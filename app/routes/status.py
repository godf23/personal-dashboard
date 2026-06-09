from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
def integration_status():
    s = get_settings()
    return {
        "proxmox_configured": s.proxmox_configured,
        "news_configured": s.news_configured,
        "owm_configured": s.owm_configured,
        "wapi_configured": s.wapi_configured,
    }
