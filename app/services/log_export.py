"""Export dashboard logs into timestamped category folders."""

from __future__ import annotations

import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR, ENV_PATH, get_settings
from app.services.debug_log import LOG_FILE, SERVICE_NAME, setup_file_logging
from app.services.restart import PID_FILE, _read_pid
from app.services.updater import get_local_commit, get_local_short_commit
from app.version import __build__, __version__

EXPORT_ROOT = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "data" / "dashboard.db"

CATEGORIES = (
    "server",
    "access",
    "errors",
    "weather",
    "news",
    "updates",
    "links",
    "system",
    "config",
    "database",
)

# Map log line -> category files (first match wins for split files)
_CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("weather", re.compile(r"weather|/api/weather|quantum|forecast|geocod", re.I)),
    ("news", re.compile(r"news|/api/news|thenewsapi|preview", re.I)),
    ("updates", re.compile(r"update|/api/updates|git pull|github", re.I)),
    ("links", re.compile(r"links|/api/links|favicon", re.I)),
    ("access", re.compile(r'"GET |"POST |"PUT |"DELETE |HTTP/1\.|uvicorn\.access', re.I)),
    ("errors", re.compile(r"\[ERROR\]|ERROR:|Traceback|Exception|500 Internal", re.I)),
]


def _timestamp_dir() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return EXPORT_ROOT / stamp


def _read_all_log_lines() -> list[str]:
    lines: list[str] = []
    if LOG_FILE.exists():
        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            lines.extend(ln.rstrip() for ln in text.splitlines())
        except OSError:
            pass

    if sys.platform != "win32":
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    SERVICE_NAME,
                    "--no-pager",
                    "-o",
                    "short-iso",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                for ln in result.stdout.strip().splitlines():
                    lines.append(ln.rstrip())
        except (OSError, subprocess.TimeoutExpired):
            pass

    return lines


def _categorize_lines(lines: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}
    buckets["server"] = list(lines)

    for line in lines:
        if not line.strip():
            continue
        placed = False
        for cat, pattern in _CATEGORY_RULES:
            if pattern.search(line):
                buckets[cat].append(line)
                placed = True
                break
        if not placed and "[WARNING]" in line.upper():
            buckets["errors"].append(line)

    return buckets


def _port_is_open(port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _detect_port() -> int | None:
    """Find a listening dashboard port without blocking on dead HTTPS handshakes."""
    for port in (443, 80, 8080):
        if not _port_is_open(port):
            continue
        schemes = ("https", "http") if port == 443 else ("http", "https")
        for scheme in schemes:
            url = f"{scheme}://127.0.0.1:{port}/api/status"
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        return port
            except (urllib.error.URLError, OSError, TimeoutError):
                continue
    return None


def _http_get_json(path: str, port: int | None) -> dict | list | None:
    if port is None:
        return None
    schemes = ("https", "http") if port == 443 else ("http", "https")
    for scheme in schemes:
        url = f"{scheme}://127.0.0.1:{port}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError):
            continue
    return None


def _system_snapshot(port: int | None = None) -> str:
    pid = _read_pid()
    commit = get_local_short_commit() or "unknown"
    full = get_local_commit() or "unknown"
    lines = [
        f"exported_at={datetime.now().isoformat()}",
        f"version={__version__}",
        f"build={__build__}",
        f"commit={commit}",
        f"commit_full={full}",
        f"pid={pid or 'not running'}",
        f"install_dir={BASE_DIR}",
        f"platform={sys.platform}",
    ]
    if PID_FILE.exists():
        try:
            lines.append(f"pid_file_mtime={datetime.fromtimestamp(PID_FILE.stat().st_mtime).isoformat()}")
        except OSError:
            pass
    status = _http_get_json("/api/status", port)
    if status:
        lines.append("")
        lines.append("--- /api/status ---")
        lines.append(json.dumps(status, indent=2))
    return "\n".join(lines) + "\n"


def _config_snapshot() -> str:
    settings = get_settings()
    safe = {
        "github_repo": settings.github_repo,
        "github_branch": settings.github_branch,
        "news_configured": settings.news_configured,
        "news_api_key_count": len(settings.news_api_token_list),
        "owm_configured": settings.owm_configured,
        "wapi_configured": settings.wapi_configured,
        "ssl_cert": settings.ssl_cert,
        "ssl_key_set": bool(settings.ssl_key),
        "env_file_exists": ENV_PATH.exists(),
    }
    lines = ["# Sanitized config (no API keys or secrets)", json.dumps(safe, indent=2)]
    return "\n".join(lines) + "\n"


def _database_snapshot() -> str:
    lines = [f"database_path={DB_PATH}", f"exists={DB_PATH.exists()}"]
    if not DB_PATH.exists():
        return "\n".join(lines) + "\n"
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        lines.append("")
        for t in tables:
            name = t["name"]
            count = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()["c"]
            lines.append(f"table {name}: {count} rows")
            if name == "links" and count:
                rows = conn.execute(
                    "SELECT id, title, url, click_count FROM links ORDER BY click_count DESC LIMIT 20"
                ).fetchall()
                lines.append("  top links by clicks:")
                for r in rows:
                    lines.append(f"    [{r['id']}] {r['title']} ({r['click_count']} clicks) {r['url']}")
            if name == "weather_locations":
                for r in conn.execute("SELECT id, label, lat, lon FROM weather_locations").fetchall():
                    lines.append(f"  weather: {r['label']} ({r['lat']}, {r['lon']})")
            if name == "news_locations":
                for r in conn.execute("SELECT id, label FROM news_locations").fetchall():
                    lines.append(f"  news: {r['label']}")
        conn.close()
    except sqlite3.Error as exc:
        lines.append(f"error reading database: {exc}")
    return "\n".join(lines) + "\n"


def _api_category_snapshots(port: int | None) -> dict[str, str]:
    out: dict[str, str] = {}
    # Skip slow endpoints during export; status-only if weather would block
    for path, key in (
        ("/api/status", "system"),
        ("/api/updates/check", "updates"),
        ("/api/links", "links"),
    ):
        data = _http_get_json(path, port)
        if data is not None:
            out[key] = json.dumps(data, indent=2) + "\n"
    return out


def export_logs() -> Path:
    """Write categorized logs to logs/<timestamp>/ and return that path."""
    setup_file_logging()
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _timestamp_dir()
    dest.mkdir(parents=True, exist_ok=True)

    all_lines = _read_all_log_lines()
    buckets = _categorize_lines(all_lines)
    port = _detect_port()
    api_snaps = _api_category_snapshots(port)

    for cat in CATEGORIES:
        path = dest / f"{cat}.log"
        parts: list[str] = []

        if cat in ("system",):
            parts.append(_system_snapshot(port))
        elif cat == "config":
            parts.append(_config_snapshot())
        elif cat == "database":
            parts.append(_database_snapshot())
        elif cat in api_snaps and cat != "system":
            parts.append(f"# Live snapshot from /api/{cat} at export time\n")
            parts.append(api_snaps[cat])

        cat_lines = buckets.get(cat, [])
        if cat_lines:
            if parts:
                parts.append("\n# --- log lines ---\n")
            parts.append("\n".join(cat_lines))
            if not parts[-1].endswith("\n"):
                parts.append("")

        if cat == "server" and LOG_FILE.exists():
            try:
                shutil.copy2(LOG_FILE, dest / "server_raw.log")
            except OSError:
                pass

        if not parts and cat != "server":
            parts.append(f"# No {cat} logs captured at {datetime.now().isoformat()}\n")

        if parts:
            path.write_text("".join(parts), encoding="utf-8")

    manifest = {
        "exported_at": datetime.now().isoformat(),
        "version": __version__,
        "build": __build__,
        "commit": get_local_short_commit(),
        "categories": list(CATEGORIES),
        "line_counts": {cat: len(buckets.get(cat, [])) for cat in CATEGORIES},
        "files": [f"{cat}.log" for cat in CATEGORIES] + ["manifest.json"],
    }
    if (dest / "server_raw.log").exists():
        manifest["files"].append("server_raw.log")

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    summary_lines = [
        f"Log export: {dest}",
        f"Build {__build__} (v{__version__})",
        "",
    ]
    for cat in CATEGORIES:
        n = len(buckets.get(cat, []))
        if n or cat in ("system", "config", "database") or cat in api_snaps:
            summary_lines.append(f"  {cat}.log  ({n} lines)" + (" + snapshot" if cat in api_snaps else ""))
    summary_lines.append("")
    summary_lines.append(f"Open folder: {dest}")

    print("\n".join(summary_lines))
    return dest
