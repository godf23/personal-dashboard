from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.database import _utcnow, get_db
from app.services.news import fetch_news_for_location
from app.services.preview import fetch_page_preview

router = APIRouter(prefix="/api/news", tags=["news"])


class LocationCreate(BaseModel):
    label: str


def _get_locations():
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM news_locations ORDER BY sort_order, id"
        ).fetchall()


@router.get("/locations")
def list_news_locations():
    rows = _get_locations()
    return [
        {"id": r["id"], "label": r["label"], "sort_order": r["sort_order"]}
        for r in rows
    ]


@router.post("/locations")
def add_news_location(body: LocationCreate):
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "Label is required")
    with get_db() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM news_locations"
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO news_locations (label, sort_order, created_at) VALUES (?, ?, ?)",
            (label, max_order + 1, _utcnow()),
        )
        row = conn.execute(
            "SELECT * FROM news_locations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return {"id": row["id"], "label": row["label"], "sort_order": row["sort_order"]}


@router.delete("/locations/{location_id}")
def delete_news_location(location_id: int):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM news_locations WHERE id = ?", (location_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Location not found")
    return {"ok": True}


@router.get("")
async def get_all_news():
    settings = get_settings()
    if not settings.news_configured:
        rows = _get_locations()
        if not rows:
            return []
        return [{"error": "Set NEWS_API_TOKEN in .env", "articles": []}]

    rows = _get_locations()
    results = []
    for row in rows:
        try:
            articles = await fetch_news_for_location(
                row["label"], settings.news_api_token
            )
            results.append({
                "id": row["id"],
                "label": row["label"],
                "articles": articles,
            })
        except Exception as e:
            results.append({
                "id": row["id"],
                "label": row["label"],
                "error": str(e),
                "articles": [],
            })
    return results


@router.get("/preview")
async def news_preview(url: str = Query(..., min_length=8)):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")
    return await fetch_page_preview(url)
