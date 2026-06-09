from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_preference, set_preference

router = APIRouter(prefix="/api/settings", tags=["settings"])

ALLOWED_KEYS = {"default_links_sort"}
ALLOWED_SORTS = {"most_used", "recent", "az", "za"}


class SettingsUpdate(BaseModel):
    default_links_sort: str | None = None


@router.get("")
def get_settings():
    return {
        "default_links_sort": get_preference("default_links_sort", "most_used"),
    }


@router.post("")
def update_settings(body: SettingsUpdate):
    data = body.model_dump(exclude_none=True)
    for key in data:
        if key not in ALLOWED_KEYS:
            raise HTTPException(400, f"Unknown preference: {key}")
    if "default_links_sort" in data and data["default_links_sort"] not in ALLOWED_SORTS:
        raise HTTPException(400, "Invalid sort mode")
    for key, value in data.items():
        set_preference(key, value)
    return get_settings()
