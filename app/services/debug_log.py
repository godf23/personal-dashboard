import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import BASE_DIR

LOG_DIR = BASE_DIR / "data"
LOG_FILE = LOG_DIR / "dashboard.log"
STARTED_FILE = LOG_DIR / "dashboard.started"
SERVICE_NAME = "personal-dashboard"

_configured = False


def setup_file_logging() -> None:
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STARTED_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(LOG_FILE) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").addHandler(handler)
    logging.getLogger("uvicorn.error").addHandler(handler)
    _configured = True
    logging.info("Dashboard started (build log active)")


def log_event(message: str, level: int = logging.INFO) -> None:
    setup_file_logging()
    logging.log(level, message)


def uptime_seconds() -> int | None:
    if STARTED_FILE.exists():
        try:
            started = datetime.fromisoformat(STARTED_FILE.read_text(encoding="utf-8").strip())
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return int((datetime.now(timezone.utc) - started).total_seconds())
        except (ValueError, OSError):
            pass
    if LOG_FILE.exists():
        try:
            age = datetime.now(timezone.utc).timestamp() - LOG_FILE.stat().st_mtime
            return max(0, int(age))
        except OSError:
            pass
    return None


def format_uptime(seconds: int | None) -> str:
    if seconds is None:
        return "⏱ --"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"⏱ {h}h {m}m {s}s"
    if m:
        return f"⏱ {m}m {s}s"
    return f"⏱ {s}s"


def tail_log_lines(max_lines: int = 80) -> list[str]:
    lines: list[str] = []
    if LOG_FILE.exists():
        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
            lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
            lines = lines[-max_lines:]
        except OSError:
            pass
    if lines:
        return lines

    if sys.platform != "win32":
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    SERVICE_NAME,
                    "-n",
                    str(max_lines),
                    "--no-pager",
                    "-o",
                    "short-iso",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return [ln.rstrip() for ln in result.stdout.strip().splitlines()][-max_lines:]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ["No logs yet. Start the dashboard with: python start.py"]
