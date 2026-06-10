import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.database import _utcnow, get_db
from app.services.news import NewsPlanLimitError, NewsRateLimitError, fetch_news_for_location
from app.services.preview import fetch_page_preview

router = APIRouter(prefix="/api/news", tags=["news"])

_news_cache: dict[str, tuple[float, list[dict]]] = {}
NEWS_CACHE_TTL = 5 * 60 * 60  # 5 hours


def _cache_key(label: str) -> str:
    return f"v3:{label}"


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
        row = conn.execute(
            "SELECT label FROM news_locations WHERE id = ?", (location_id,)
        ).fetchone()
        cur = conn.execute(
            "DELETE FROM news_locations WHERE id = ?", (location_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Location not found")
    if row:
        _news_cache.pop(_cache_key(row["label"]), None)
    return {"ok": True}


async def _news_for_location(
    label: str,
    tokens: list[str],
    *,
    refresh: bool = False,
) -> tuple[list[dict], int | None]:
    key = _cache_key(label)
    now = time.time()
    if not refresh and key in _news_cache:
        cached_at, articles = _news_cache[key]
        if now - cached_at < NEWS_CACHE_TTL:
            return articles, None
    articles, token_index = await fetch_news_for_location(label, tokens)
    _news_cache[key] = (now, articles)
    return articles, token_index


@router.get("")
async def get_all_news(refresh: bool = False):
    settings = get_settings()
    tokens = settings.news_api_token_list
    if not settings.news_configured:
        rows = _get_locations()
        if not rows:
            return []
        return [{"error": "Set NEWS_API_TOKEN in .env", "articles": []}]

    rows = _get_locations()
    results = []
    for row in rows:
        try:
            articles, token_index = await _news_for_location(
                row["label"], tokens, refresh=refresh
            )
            cached_at = _news_cache.get(_cache_key(row["label"]), (0,))[0]
            entry = {
                "id": row["id"],
                "label": row["label"],
                "articles": articles,
                "cached": not refresh and (time.time() - cached_at) < NEWS_CACHE_TTL,
            }
            if token_index is not None and token_index > 0:
                entry["api_key_index"] = token_index + 1
            results.append(entry)
        except (NewsRateLimitError, NewsPlanLimitError) as e:
            results.append({
                "id": row["id"],
                "label": row["label"],
                "error": f"All news API keys exhausted: {e}",
                "articles": [],
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
