#!/usr/bin/env python3
"""Stage, commit, and push dashboard source changes to GitHub."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "app" / "version.py"
REMOTE = "origin"
BRANCH = "main"
DEFAULT_GIT_NAME = "godf23"
DEFAULT_GIT_EMAIL = "godf23@users.noreply.github.com"

# Only project source is staged; runtime paths are covered by .gitignore.
SOURCE_PATHS = (
    "app",
    "scripts",
    "install",
    ".gitignore",
    ".env.example",
    "README.md",
    "requirements.txt",
    "dash.py",
    "start.py",
    "dash.bat",
    "dash.ps1",
    "push.bat",
    "push.ps1",
)


def run(cmd: list[str], *, check: bool = True, env: dict | None = None) -> int:
    print(f"> {' '.join(cmd)}")
    kwargs = {"cwd": ROOT, "text": True}
    if env is not None:
        kwargs["env"] = env
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def capture(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def git_identity_env() -> dict | None:
    """Supply author info for this commit only when git has no global identity."""
    import os

    name = subprocess.run(
        ["git", "config", "user.name"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if name and email:
        return None

    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", name or DEFAULT_GIT_NAME)
    env.setdefault("GIT_AUTHOR_EMAIL", email or DEFAULT_GIT_EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    if not name or not email:
        print(f"Using commit identity: {env['GIT_AUTHOR_NAME']} <{env['GIT_AUTHOR_EMAIL']}>")
    return env


def bump_version() -> str:
    sys.path.insert(0, str(ROOT))
    from app.version import __build__, bump_build

    new_build = bump_build(__build__)
    text = VERSION_FILE.read_text(encoding="utf-8")
    text = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_build}"', text, count=1)
    text = re.sub(r'__build__ = "[^"]+"', f'__build__ = "{new_build}"', text, count=1)
    VERSION_FILE.write_text(text, encoding="utf-8")
    print(f"Bumped version to {new_build}")
    return new_build


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def untrack_ignored_files() -> list[str]:
    """Drop tracked files that are now listed in .gitignore (logs, data, .env, etc.)."""
    tracked = capture(["git", "ls-files", "-z"]).split("\0")
    removed: list[str] = []
    for path in tracked:
        if not path or not is_ignored(path):
            continue
        run(["git", "rm", "--cached", "-f", path], check=False)
        removed.append(path)
    if removed:
        print(f"Removed {len(removed)} ignored file(s) from git tracking:")
        for path in removed[:8]:
            print(f"  - {path}")
        if len(removed) > 8:
            print(f"  ... and {len(removed) - 8} more")
    return removed


def stage_source_changes() -> None:
    existing = [path for path in SOURCE_PATHS if (ROOT / path).exists()]
    if not existing:
        print("Error: no source paths found to stage.")
        sys.exit(1)
    run(["git", "add", "--", *existing])


def has_changes() -> bool:
    return bool(capture(["git", "status", "--porcelain"]).strip())


def show_staged_summary() -> None:
    summary = capture(["git", "diff", "--cached", "--stat"]).strip()
    if summary:
        print(summary)
        print()


def main() -> None:
    message = " ".join(sys.argv[1:]).strip()
    if not message:
        message = input("Commit message: ").strip()
    if not message:
        print("Aborted: commit message required.")
        sys.exit(1)

    if not (ROOT / ".git").is_dir():
        print("Error: not a git repository.")
        sys.exit(1)

    untrack_ignored_files()
    new_build = bump_version()

    if has_changes():
        stage_source_changes()
        show_staged_summary()
        run(["git", "commit", "-m", message], env=git_identity_env())
    else:
        print("No local changes to commit (version file already staged).")

    print(f"Release build: {new_build}")

    run(["git", "push", "-u", REMOTE, BRANCH])
    print()
    print(f"Pushed to https://github.com/godf23/personal-dashboard ({BRANCH})")
    print("Running dashboards will pick up the update within a few minutes.")


if __name__ == "__main__":
    main()
