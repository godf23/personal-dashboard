from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_db, _utcnow
from app.services.favicon import favicon_url_for

router = APIRouter(prefix="/api/links", tags=["links"])

SORT_MODES = {"most_used", "recent", "az", "za"}


class LinkCreate(BaseModel):
    title: str
    url: str


class LinkOut(BaseModel):
    id: int
    title: str
    url: str
    icon_url: str | None
    click_count: int
    last_clicked_at: str | None
    created_at: str


def _row_to_link(row) -> dict:
    icon = row["icon_url"]
    if not icon:
        icon = favicon_url_for(row["url"])
    return {
        "id": row["id"],
        "title": row["title"],
        "url": row["url"],
        "icon_url": icon,
        "click_count": row["click_count"],
        "last_clicked_at": row["last_clicked_at"],
        "created_at": row["created_at"],
    }


def _order_clause(sort: str) -> str:
    title_az = "title COLLATE NOCASE ASC"
    title_za = "title COLLATE NOCASE DESC"
    if sort == "most_used":
        return f"click_count DESC, {title_az}"
    if sort == "recent":
        return f"last_clicked_at DESC NULLS LAST, {title_az}"
    if sort == "az":
        return title_az
    if sort == "za":
        return title_za
    return title_az


@router.get("")
def list_links(sort: str = "most_used"):
    if sort not in SORT_MODES:
        sort = "most_used"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM links ORDER BY {_order_clause(sort)}"
        ).fetchall()
    return [_row_to_link(r) for r in rows]


@router.post("")
def create_link(body: LinkCreate):
    title = body.title.strip()
    url = body.url.strip()
    if not title or not url:
        raise HTTPException(400, "Title and URL are required")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    icon_url = favicon_url_for(url)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO links (title, url, icon_url, created_at) VALUES (?, ?, ?, ?)",
            (title, url, icon_url, _utcnow()),
        )
        row = conn.execute(
            "SELECT * FROM links WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_link(row)


@router.delete("/{link_id}")
def delete_link(link_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Link not found")
    return {"ok": True}


@router.post("/{link_id}/click")
def click_link(link_id: int):
    now = _utcnow()
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE links SET click_count = click_count + 1, last_clicked_at = ? WHERE id = ?",
            (now, link_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Link not found")
        row = conn.execute("SELECT url FROM links WHERE id = ?", (link_id,)).fetchone()
    return {"url": row["url"]}
