import asyncio
import subprocess
import time
from pathlib import Path

import httpx

from app.config import BASE_DIR

DEFAULT_REPO = "godf23/personal-dashboard"
DEFAULT_BRANCH = "main"
UPDATE_SCRIPT = BASE_DIR / "scripts" / "update.sh"
SERVICE_NAME = "personal-dashboard"

_cache: dict = {"at": 0.0, "data": None}
CACHE_TTL = 300


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def is_git_install() -> bool:
    return (BASE_DIR / ".git").is_dir() and _run_git("rev-parse", "HEAD") is not None


def get_local_commit() -> str | None:
    return _run_git("rev-parse", "HEAD")


def get_local_short_commit() -> str | None:
    return _run_git("rev-parse", "--short", "HEAD")


async def _fetch_remote_commit(repo: str, branch: str) -> dict | None:
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    commit = data.get("commit", {})
    return {
        "sha": data.get("sha", ""),
        "short_sha": (data.get("sha") or "")[:7],
        "message": (commit.get("message") or "").split("\n")[0],
        "date": commit.get("author", {}).get("date", ""),
        "url": data.get("html_url", ""),
    }


async def check_for_update(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    *,
    force: bool = False,
) -> dict:
    now = time.time()
    if (
        not force
        and _cache["data"] is not None
        and now - _cache["at"] < CACHE_TTL
    ):
        return _cache["data"]

    local = get_local_commit()
    local_short = get_local_short_commit()
    supported = is_git_install()

    payload = {
        "updates_supported": supported,
        "local_sha": local,
        "local_short_sha": local_short,
        "remote_sha": None,
        "remote_short_sha": None,
        "update_available": False,
        "message": "",
        "published_at": "",
        "repo": repo,
        "branch": branch,
        "error": None,
    }

    if not supported:
        payload["error"] = "Not a git install — updates unavailable"
        _cache["at"] = now
        _cache["data"] = payload
        return payload

    remote = await _fetch_remote_commit(repo, branch)
    if not remote or not remote.get("sha"):
        payload["error"] = "Could not reach GitHub"
        _cache["at"] = now
        _cache["data"] = payload
        return payload

    payload.update({
        "remote_sha": remote["sha"],
        "remote_short_sha": remote["short_sha"],
        "message": remote["message"],
        "published_at": remote["date"],
        "update_available": local != remote["sha"],
    })

    _cache["at"] = now
    _cache["data"] = payload
    return payload


def _pip_install() -> tuple[bool, str]:
    venv_pip = BASE_DIR / ".venv" / "bin" / "pip"
    if not venv_pip.exists():
        venv_pip = BASE_DIR / ".venv" / "Scripts" / "pip.exe"
    if not venv_pip.exists():
        return False, "Virtual environment pip not found"

    try:
        result = subprocess.run(
            [str(venv_pip), "install", "-r", "requirements.txt", "-q"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "pip failed").strip()
            return False, err[:500]
        return True, ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _git_pull_hard(branch: str) -> tuple[bool, str]:
    fetch = subprocess.run(
        ["git", "fetch", "origin", branch],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if fetch.returncode != 0:
        err = (fetch.stderr or fetch.stdout or "git fetch failed").strip()
        return False, err[:500]

    reset = subprocess.run(
        ["git", "reset", "--hard", f"origin/{branch}"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if reset.returncode != 0:
        err = (reset.stderr or reset.stdout or "git reset failed").strip()
        return False, err[:500]
    return True, ""


def _try_systemd_restart() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "restart", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def apply_update_sync(branch: str = DEFAULT_BRANCH) -> dict:
    if not is_git_install():
        return {"ok": False, "error": "Not a git install"}

    used_script = False
    if UPDATE_SCRIPT.exists():
        try:
            result = subprocess.run(
                ["bash", str(UPDATE_SCRIPT), branch],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            if result.returncode == 0:
                used_script = True
            elif result.returncode != 0:
                err = (result.stderr or result.stdout or "update script failed").strip()
                # Fall back to inline update when bash is unavailable (e.g. Windows)
                if "bash" not in err.lower() and "not found" not in err.lower():
                    return {"ok": False, "error": err[:500]}
        except FileNotFoundError:
            pass
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}

    if not used_script:
        ok, err = _git_pull_hard(branch)
        if not ok:
            return {"ok": False, "error": err}
        ok, err = _pip_install()
        if not ok:
            return {"ok": False, "error": err}

    restarted = _try_systemd_restart()
    _cache["data"] = None
    return {
        "ok": True,
        "restarted": restarted,
        "restart_required": not restarted,
        "local_short_sha": get_local_short_commit(),
    }


async def apply_update(branch: str = DEFAULT_BRANCH) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, apply_update_sync, branch)
