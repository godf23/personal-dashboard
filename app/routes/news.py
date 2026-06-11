import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import _utcnow, get_db
from app.services.news import NewsPlanLimitError, NewsRateLimitError, fetch_news_for_location
from app.services.news_pipeline import collect_discovery, process_feed
from app.services.news_prefs import (
    delete_saved_article,
    get_age_filter,
    get_all_prefs,
    list_saved_articles,
    mark_all_read,
    mark_read,
    save_article,
    update_prefs,
    update_saved_article,
)
from app.services.preview import fetch_page_preview

router = APIRouter(prefix="/api/news", tags=["news"])

_news_cache: dict[str, tuple[float, list[dict]]] = {}
_discovery: dict[str, set[str]] = {"sources": set(), "categories": set()}
NEWS_CACHE_TTL = 5 * 60 * 60  # 5 hours


def _cache_key(label: str) -> str:
    return f"v4:{label}"


class LocationCreate(BaseModel):
    label: str


class ReadBody(BaseModel):
    url: str


class ReadAllBody(BaseModel):
    urls: list[str] = Field(default_factory=list)


class NewsPrefsUpdate(BaseModel):
    age_filter: dict | None = None
    keyword_blacklist: list[str] | None = None
    source_prefs: dict[str, int] | None = None
    category_prefs: dict[str, bool] | None = None


class SavedArticleCreate(BaseModel):
    url: str
    title: str = ""
    source: str | None = None
    description: str | None = None
    image_url: str | None = None
    published_at: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SavedArticlePatch(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None


def _get_locations():
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM news_locations ORDER BY sort_order, id"
        ).fetchall()


def _rebuild_discovery() -> None:
    sources: set[str] = set()
    categories: set[str] = set()
    for _, articles in _news_cache.values():
        s, c = collect_discovery(articles)
        sources |= s
        categories |= c
    _discovery["sources"] = sources
    _discovery["categories"] = categories


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
        _rebuild_discovery()
    return {"ok": True}


async def _raw_news_for_location(
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

    age = get_age_filter()
    days = int(age.get("days", 7))
    articles, token_index = await fetch_news_for_location(label, tokens, days=days)
    _news_cache[key] = (now, articles)
    _rebuild_discovery()
    return articles, token_index


@router.get("/prefs")
def get_news_prefs():
    return get_all_prefs()


@router.post("/prefs")
def post_news_prefs(body: NewsPrefsUpdate):
    partial = body.model_dump(exclude_unset=True)
    return update_prefs(partial)


@router.get("/sources")
def list_news_sources():
    return sorted(_discovery.get("sources", set()))


@router.get("/categories")
def list_news_categories():
    return sorted(_discovery.get("categories", set()))


@router.post("/read")
def post_mark_read(body: ReadBody):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")
    mark_read(url)
    return {"ok": True}


@router.post("/read/all")
def post_mark_all_read(body: ReadAllBody):
    count = mark_all_read(body.urls)
    return {"ok": True, "count": count}


@router.get("/saved")
def get_saved(tag: str | None = None):
    return list_saved_articles(tag)


@router.post("/saved")
def post_saved(body: SavedArticleCreate):
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")
    return save_article(body.model_dump())


@router.patch("/saved/{article_id}")
def patch_saved(article_id: int, body: SavedArticlePatch):
    updated = update_saved_article(
        article_id,
        notes=body.notes,
        tags=body.tags,
    )
    if not updated:
        raise HTTPException(404, "Saved article not found")
    return updated


@router.delete("/saved/{article_id}")
def delete_saved(article_id: int):
    if not delete_saved_article(article_id):
        raise HTTPException(404, "Saved article not found")
    return {"ok": True}


@router.get("")
async def get_all_news(refresh: bool = Query(False)):
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
            raw_articles, token_index = await _raw_news_for_location(
                row["label"], tokens, refresh=refresh
            )
            items = process_feed(raw_articles)
            cached_at = _news_cache.get(_cache_key(row["label"]), (0,))[0]
            entry = {
                "id": row["id"],
                "label": row["label"],
                "articles": items,
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
