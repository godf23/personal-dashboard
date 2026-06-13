import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.config import BASE_DIR

SERVICE_NAME = "personal-dashboard"
WINDOWS_TASK_NAME = "PersonalDashboard"
START_SCRIPT = BASE_DIR / "start.py"
PID_FILE = BASE_DIR / "data" / "dashboard.pid"
SERVICE_TEMPLATE = BASE_DIR / "install" / "personal-dashboard.service"
SYSTEMD_UNIT_PATH = Path(f"/etc/systemd/system/{SERVICE_NAME}.service")


def _python_executable() -> str:
    for candidate in (
        BASE_DIR / ".venv" / "Scripts" / "python.exe",
        BASE_DIR / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


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


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return str(pid) in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_dashboard_running() -> bool:
    pid = _read_pid()
    if pid and _is_process_alive(pid):
        return True
    if _systemd_is_active():
        return True
    return False


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


def _run_systemctl(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["systemctl", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _systemd_unit_exists() -> bool:
    result = _run_systemctl("cat", SERVICE_NAME)
    return result is not None and result.returncode == 0


def _systemd_is_active() -> bool:
    result = _run_systemctl("is-active", SERVICE_NAME)
    return result is not None and result.stdout.strip() == "active"


def _systemd_is_enabled() -> bool:
    result = _run_systemctl("is-enabled", SERVICE_NAME)
    if result is None:
        return False
    state = result.stdout.strip()
    return state in ("enabled", "enabled-runtime")


def _systemd_start() -> bool:
    result = _run_systemctl("start", SERVICE_NAME)
    return result is not None and result.returncode == 0


def _systemd_restart() -> bool:
    result = _run_systemctl("restart", SERVICE_NAME)
    return result is not None and result.returncode == 0


def _systemd_enable() -> bool:
    result = _run_systemctl("enable", SERVICE_NAME)
    return result is not None and result.returncode == 0


def _systemd_disable() -> bool:
    result = _run_systemctl("disable", SERVICE_NAME)
    return result is not None and result.returncode == 0


def _render_systemd_unit() -> str:
    template = SERVICE_TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("INSTALL_DIR", str(BASE_DIR))
        .replace("PYTHON_BIN", _python_executable())
        .replace("START_SCRIPT", str(START_SCRIPT))
    )


def _install_systemd_unit() -> tuple[bool, str]:
    if sys.platform == "win32":
        return False, "systemd is not available on Windows"
    if not SERVICE_TEMPLATE.exists():
        return False, f"Missing service template: {SERVICE_TEMPLATE}"

    unit_body = _render_systemd_unit()
    unit_path = SYSTEMD_UNIT_PATH

    try:
        if os.geteuid() == 0:
            unit_path.write_text(unit_body, encoding="utf-8")
        else:
            write = subprocess.run(
                ["sudo", "tee", str(unit_path)],
                input=unit_body,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if write.returncode != 0:
                err = (write.stderr or write.stdout or "sudo tee failed").strip()
                return False, err[:300]
        reload = subprocess.run(
            ["systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if reload.returncode != 0:
            return False, "systemctl daemon-reload failed"
        return True, str(unit_path)
    except OSError as exc:
        return False, str(exc)


def _spawn_server() -> bool:
    try:
        log_path = BASE_DIR / "data" / "dashboard-spawn.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        python_bin = _python_executable()

        if sys.platform == "win32":
            # start /B keeps the child alive after this CLI exits; append server output to a log file.
            cmd = (
                f'start "" /B "{python_bin}" "{START_SCRIPT}" '
                f'>> "{log_path}" 2>&1'
            )
            subprocess.Popen(cmd, shell=True, cwd=BASE_DIR)
            return True

        with open(log_path, "a", encoding="utf-8") as log_file:
            subprocess.Popen(
                [python_bin, str(START_SCRIPT)],
                cwd=BASE_DIR,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return True
    except OSError:
        return False


def start_dashboard() -> dict:
    """Start the dashboard in the background if it is not already running."""
    if is_dashboard_running():
        return {"ok": True, "message": "Dashboard is already running.", "already_running": True}

    if _systemd_unit_exists():
        if _systemd_start():
            time.sleep(1)
            if is_dashboard_running():
                return {"ok": True, "message": "Dashboard started via systemd."}
        return {"ok": False, "error": "systemctl start failed — check: journalctl -u personal-dashboard -n 50"}

    if not START_SCRIPT.exists():
        return {"ok": False, "error": "start.py not found"}

    if not _spawn_server():
        return {"ok": False, "error": "Could not start dashboard process"}

    for _ in range(10):
        time.sleep(0.5)
        if is_dashboard_running():
            pid = _read_pid()
            suffix = f" (pid {pid})" if pid else ""
            return {"ok": True, "message": f"Dashboard started in background{suffix}."}

    return {
        "ok": True,
        "message": (
            "Dashboard process launched — check data/dashboard-spawn.log if the site does not load."
        ),
    }


def restart_dashboard() -> dict:
    """Restart from a separate terminal."""
    if _systemd_unit_exists():
        if _systemd_restart():
            return {"ok": True, "message": "Service restarted via systemd."}
        return {"ok": False, "error": "systemctl restart failed"}

    pid = _read_pid()
    if pid and pid != os.getpid():
        _kill_pid(pid)
        clear_pid()
        time.sleep(1)

    return start_dashboard()


def dashboard_status() -> dict:
    pid = _read_pid()
    alive = pid is not None and _is_process_alive(pid) if pid else False
    return {
        "running": is_dashboard_running(),
        "pid": pid if alive else None,
        "systemd": _systemd_unit_exists(),
        "systemd_active": _systemd_is_active(),
        "systemd_enabled": _systemd_is_enabled(),
        "windows_task": _windows_task_exists() if sys.platform == "win32" else False,
    }


def _windows_task_exists() -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", WINDOWS_TASK_NAME],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def enable_autostart() -> dict:
    """Register dashboard to start automatically when the machine boots."""
    if sys.platform == "win32":
        return _enable_windows_autostart()

    if not _systemd_unit_exists():
        ok, detail = _install_systemd_unit()
        if not ok:
            return {"ok": False, "error": detail}

    if not _systemd_enable():
        return {"ok": False, "error": "systemctl enable failed (try with sudo)"}

    if not is_dashboard_running():
        start_dashboard()

    return {
        "ok": True,
        "message": (
            f"Autostart enabled ({SERVICE_NAME}). "
            "Dashboard will start on boot and after crashes (Restart=on-failure)."
        ),
    }


def disable_autostart() -> dict:
    if sys.platform == "win32":
        return _disable_windows_autostart()
    if not _systemd_disable():
        return {"ok": False, "error": "systemctl disable failed"}
    return {"ok": True, "message": f"Autostart disabled for {SERVICE_NAME}."}


def _enable_windows_autostart() -> dict:
    python_bin = _python_executable()
    tr = f'"{python_bin}" "{START_SCRIPT}"'
    try:
        result = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                WINDOWS_TASK_NAME,
                "/TR",
                tr,
                "/SC",
                "ONLOGON",
                "/RL",
                "LIMITED",
                "/F",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "schtasks failed").strip()
            return {"ok": False, "error": err[:400]}
        if not is_dashboard_running():
            start_dashboard()
        return {
            "ok": True,
            "message": (
                f"Autostart enabled (Task Scheduler: {WINDOWS_TASK_NAME}). "
                "Dashboard starts when you log in to Windows."
            ),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}


def _disable_windows_autostart() -> dict:
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "schtasks delete failed").strip()
            return {"ok": False, "error": err[:400]}
        return {"ok": True, "message": f"Removed Windows autostart task ({WINDOWS_TASK_NAME})."}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}
