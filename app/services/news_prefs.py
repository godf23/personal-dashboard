"""News personalization preferences stored in SQLite."""

from __future__ import annotations

import json

from app.database import _utcnow, get_db, get_preference, set_preference

DEFAULT_AGE_FILTER = {"mode": "7d", "days": 7}


def _parse_json(value: str, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def get_age_filter() -> dict:
    return _parse_json(get_preference("news_age_filter"), dict(DEFAULT_AGE_FILTER))


def set_age_filter(prefs: dict) -> dict:
    mode = prefs.get("mode", "7d")
    days = int(prefs.get("days", 7))
    if mode == "24h":
        days = 1
    elif mode == "7d":
        days = 7
    elif mode == "30d":
        days = 30
    payload = {"mode": mode, "days": max(1, days)}
    set_preference("news_age_filter", json.dumps(payload))
    return payload


def get_keyword_blacklist() -> list[str]:
    raw = _parse_json(get_preference("news_keyword_blacklist"), [])
    return [str(k).strip().lower() for k in raw if str(k).strip()]


def set_keyword_blacklist(keywords: list[str]) -> list[str]:
    cleaned = []
    for k in keywords:
        word = str(k).strip().lower()
        if word and word not in cleaned:
            cleaned.append(word)
    set_preference("news_keyword_blacklist", json.dumps(cleaned))
    return cleaned


def get_source_prefs() -> dict[str, int]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT source, weight FROM news_source_prefs ORDER BY source"
        ).fetchall()
    return {r["source"]: int(r["weight"]) for r in rows}


def set_source_pref(source: str, weight: int) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO news_source_prefs (source, weight) VALUES (?, ?)
            ON CONFLICT(source) DO UPDATE SET weight = excluded.weight
            """,
            (source.strip(), int(weight)),
        )


def get_category_prefs() -> dict[str, bool]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT category, enabled FROM news_category_prefs ORDER BY category"
        ).fetchall()
    return {r["category"]: bool(r["enabled"]) for r in rows}


def ensure_categories_seen(categories: set[str]) -> None:
    if not categories:
        return
    with get_db() as conn:
        for cat in sorted(categories):
            conn.execute(
                """
                INSERT OR IGNORE INTO news_category_prefs (category, enabled)
                VALUES (?, 1)
                """,
                (cat,),
            )


def set_category_pref(category: str, enabled: bool) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO news_category_prefs (category, enabled) VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET enabled = excluded.enabled
            """,
            (category.strip(), 1 if enabled else 0),
        )


def get_all_prefs() -> dict:
    return {
        "age_filter": get_age_filter(),
        "keyword_blacklist": get_keyword_blacklist(),
        "source_prefs": get_source_prefs(),
        "category_prefs": get_category_prefs(),
    }


def update_prefs(partial: dict) -> dict:
    if "age_filter" in partial and partial["age_filter"] is not None:
        set_age_filter(partial["age_filter"])
    if "keyword_blacklist" in partial and partial["keyword_blacklist"] is not None:
        set_keyword_blacklist(partial["keyword_blacklist"])
    if "source_prefs" in partial and partial["source_prefs"] is not None:
        for source, weight in partial["source_prefs"].items():
            set_source_pref(source, int(weight))
    if "category_prefs" in partial and partial["category_prefs"] is not None:
        for category, enabled in partial["category_prefs"].items():
            set_category_pref(category, bool(enabled))
    return get_all_prefs()


def mark_read(url: str) -> None:
    if not url:
        return
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO news_read (url, read_at) VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE SET read_at = excluded.read_at
            """,
            (url, _utcnow()),
        )


def mark_all_read(urls: list[str]) -> int:
    count = 0
    for url in urls:
        if url:
            mark_read(url)
            count += 1
    return count


def get_read_urls() -> set[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT url FROM news_read").fetchall()
    return {r["url"] for r in rows}


def get_saved_urls() -> set[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT url FROM saved_articles").fetchall()
    return {r["url"] for r in rows}


def list_saved_articles(tag: str | None = None) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_articles ORDER BY saved_at DESC"
        ).fetchall()
    items = []
    for r in rows:
        tags = _parse_json(r["tags"], [])
        if tag and tag not in tags:
            continue
        items.append(
            {
                "id": r["id"],
                "url": r["url"],
                "title": r["title"],
                "source": r["source"],
                "description": r["description"],
                "image_url": r["image_url"],
                "published_at": r["published_at"],
                "notes": r["notes"],
                "tags": tags,
                "saved_at": r["saved_at"],
            }
        )
    return items


def save_article(data: dict) -> dict:
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    now = _utcnow()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO saved_articles (
                url, title, source, description, image_url, published_at,
                notes, tags, saved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                description = excluded.description,
                image_url = excluded.image_url,
                published_at = excluded.published_at,
                notes = COALESCE(excluded.notes, saved_articles.notes),
                tags = excluded.tags,
                saved_at = saved_articles.saved_at
            """,
            (
                data["url"],
                data.get("title", ""),
                data.get("source"),
                data.get("description"),
                data.get("image_url"),
                data.get("published_at"),
                data.get("notes"),
                json.dumps(tags),
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM saved_articles WHERE url = ?", (data["url"],)
        ).fetchone()
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "source": row["source"],
        "description": row["description"],
        "image_url": row["image_url"],
        "published_at": row["published_at"],
        "notes": row["notes"],
        "tags": _parse_json(row["tags"], []),
        "saved_at": row["saved_at"],
    }


def update_saved_article(article_id: int, notes: str | None = None, tags: list | None = None) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM saved_articles WHERE id = ?", (article_id,)
        ).fetchone()
        if not row:
            return None
        new_notes = notes if notes is not None else row["notes"]
        new_tags = json.dumps(tags if tags is not None else _parse_json(row["tags"], []))
        conn.execute(
            "UPDATE saved_articles SET notes = ?, tags = ? WHERE id = ?",
            (new_notes, new_tags, article_id),
        )
        row = conn.execute(
            "SELECT * FROM saved_articles WHERE id = ?", (article_id,)
        ).fetchone()
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "source": row["source"],
        "description": row["description"],
        "image_url": row["image_url"],
        "published_at": row["published_at"],
        "notes": row["notes"],
        "tags": _parse_json(row["tags"], []),
        "saved_at": row["saved_at"],
    }


def delete_saved_article(article_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM saved_articles WHERE id = ?", (article_id,))
        return cur.rowcount > 0
