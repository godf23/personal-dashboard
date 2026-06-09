from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services.restart import restart_dashboard_sync
from app.services.updater import apply_update, check_for_update
from app.version import __build__, __name__ as app_name, __version__

router = APIRouter(prefix="/api/cli", tags=["cli"])

COMMANDS = {
    "help": "List commands: /help, /version, /update, /restart",
    "version": "Show build version",
    "update": "Pull latest code from GitHub",
    "restart": "Restart the dashboard",
}


class CliRequest(BaseModel):
    command: str


def _normalize(raw: str) -> str:
    cmd = raw.strip().lower()
    if cmd.startswith("/"):
        cmd = cmd[1:]
    return cmd.split()[0] if cmd else ""


@router.get("/commands")
def list_commands():
    return {
        "commands": [
            {"name": f"/{name}", "description": desc}
            for name, desc in COMMANDS.items()
        ]
    }


@router.get("/version")
def version_info():
    from app.services.updater import get_local_short_commit

    return {
        "name": app_name,
        "version": __version__,
        "build": __build__,
        "commit": get_local_short_commit(),
    }


@router.post("")
async def run_command(body: CliRequest, background_tasks: BackgroundTasks):
    cmd = _normalize(body.command)
    if not cmd:
        raise HTTPException(400, "Empty command")

    if cmd == "help":
        return {
            "ok": True,
            "output": "\n".join(f"/{k} — {v}" for k, v in COMMANDS.items()),
        }

    if cmd == "version":
        info = version_info()
        return {
            "ok": True,
            "output": (
                f"{info['name']}  build {info['build']}  (v{info['version']})"
                + (f"  [{info['commit']}]" if info.get("commit") else "")
            ),
        }

    if cmd == "update":
        settings = get_settings()
        status = await check_for_update(
            settings.github_repo, settings.github_branch, force=True
        )
        if not status.get("updates_supported"):
            raise HTTPException(400, status.get("error") or "Updates not supported")
        if not status.get("update_available"):
            return {"ok": True, "output": "Already on the latest build."}

        result = await apply_update(settings.github_branch)
        if not result.get("ok"):
            raise HTTPException(500, result.get("error", "Update failed"))

        sha = result.get("local_short_sha", "latest")
        if result.get("restarted"):
            return {"ok": True, "output": f"Updated to {sha}. Restarting…", "restarting": True}
        if result.get("restart_required"):
            return {
                "ok": True,
                "output": f"Updated to {sha}. Run /restart to apply.",
                "restart_suggested": True,
            }
        return {"ok": True, "output": f"Updated to {sha}."}

    if cmd == "restart":
        def _restart():
            restart_dashboard_sync()

        background_tasks.add_task(_restart)
        return {"ok": True, "output": "Restarting dashboard…", "restarting": True}

    raise HTTPException(400, f"Unknown command: /{cmd}. Type /help")
