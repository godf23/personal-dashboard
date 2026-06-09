from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services.updater import apply_update, check_for_update

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("/check")
async def updates_check():
    settings = get_settings()
    return await check_for_update(settings.github_repo, settings.github_branch)


@router.post("/apply")
async def updates_apply():
    settings = get_settings()
    status = await check_for_update(
        settings.github_repo, settings.github_branch, force=True
    )
    if not status.get("updates_supported"):
        raise HTTPException(400, status.get("error") or "Updates not supported")
    if not status.get("update_available"):
        return {"ok": True, "message": "Already up to date", "restarted": False}

    result = await apply_update(settings.github_branch)
    if not result.get("ok"):
        raise HTTPException(500, result.get("error", "Update failed"))
    return result
