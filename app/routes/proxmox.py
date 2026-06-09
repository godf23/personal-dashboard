from fastapi import APIRouter

from app.config import get_settings
from app.services.proxmox import get_proxmox_stats

router = APIRouter(prefix="/api/proxmox", tags=["proxmox"])


@router.get("/stats")
async def proxmox_stats():
    settings = get_settings()
    return await get_proxmox_stats(settings)
