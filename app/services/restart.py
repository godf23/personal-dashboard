import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config import BASE_DIR

SERVICE_NAME = "personal-dashboard"
START_SCRIPT = BASE_DIR / "start.py"
PID_FILE = BASE_DIR / "data" / "dashboard.pid"


def write_pid() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _systemd_restart() -> bool:
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


def _spawn_server() -> bool:
    try:
        kwargs: dict = {
            "cwd": BASE_DIR,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([sys.executable, str(START_SCRIPT)], **kwargs)
        return True
    except OSError:
        return False


def restart_dashboard() -> dict:
    """Restart from a separate terminal."""
    if _systemd_restart():
        return {"ok": True, "message": "Service restarted via systemd."}

    pid = _read_pid()
    if pid and pid != os.getpid():
        _kill_pid(pid)
        time.sleep(1)

    if not START_SCRIPT.exists():
        return {"ok": False, "error": "start.py not found"}

    if not _spawn_server():
        return {"ok": False, "error": "Could not start dashboard"}

    return {"ok": True, "message": "Dashboard restarted."}
