import os
import subprocess
import sys
import time
from pathlib import Path

from app.config import BASE_DIR

SERVICE_NAME = "personal-dashboard"
START_SCRIPT = BASE_DIR / "start.py"


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


def _spawn_fresh_process() -> bool:
    try:
        kwargs: dict = {
            "cwd": BASE_DIR,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen([sys.executable, str(START_SCRIPT)], **kwargs)
        return True
    except OSError:
        return False


def restart_from_cli() -> dict:
    """Restart when invoked from a separate terminal (systemd only)."""
    if _systemd_restart():
        return {"ok": True, "message": "Service restarted."}
    return {
        "ok": False,
        "error": "Use /restart in the dashboard, or stop and run: python start.py",
    }


def restart_dashboard_sync() -> dict:
    if _systemd_restart():
        return {"ok": True, "method": "systemd", "message": "Service restarting…"}

    if not START_SCRIPT.exists():
        return {"ok": False, "error": "start.py not found"}

    if not _spawn_fresh_process():
        return {"ok": False, "error": "Could not spawn new process"}

    time.sleep(0.8)
    os._exit(0)
