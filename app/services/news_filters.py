"""News feed filtering and duplicate clustering."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

STOP_WORDS = frozenset(
    "a an the and or but in on at to for of is are was were be been being "
    "with from by as it its this that these those".split()
)

DEDUP_RATIO = 0.88


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def title_fingerprint(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    words = [w for w in t.split() if w and w not in STOP_WORDS]
    return " ".join(words)


def apply_age_filter(articles: list[dict], age_prefs: dict) -> list[dict]:
    days = int(age_prefs.get("days", 7))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for article in articles:
        published = _parse_published_at(article.get("published_at", ""))
        if published is None or published < cutoff:
            continue
        out.append(article)
    return out


def apply_keyword_blacklist(articles: list[dict], keywords: list[str]) -> list[dict]:
    if not keywords:
        return articles
    out = []
    for article in articles:
        blob = f"{article.get('title', '')} {article.get('description', '')}".lower()
        if any(kw in blob for kw in keywords):
            continue
        out.append(article)
    return out


def _source_weight(source: str, prefs: dict[str, int]) -> int:
    return int(prefs.get(source, 0))


def apply_source_prefs(articles: list[dict], prefs: dict[str, int]) -> list[dict]:
    filtered = [a for a in articles if _source_weight(a.get("source", ""), prefs) != -1]

    def sort_key(article: dict) -> tuple:
        weight = _source_weight(article.get("source", ""), prefs)
        priority = 0 if weight >= 1 else (1 if weight == 0 else 2)
        published = _parse_published_at(article.get("published_at", ""))
        ts = published or datetime.min.replace(tzinfo=timezone.utc)
        return (priority, -ts.timestamp())

    filtered.sort(key=sort_key)
    return filtered


def apply_category_prefs(articles: list[dict], prefs: dict[str, bool]) -> list[dict]:
    if not prefs:
        return articles
    out = []
    for article in articles:
        cats = article.get("categories") or []
        if not cats:
            out.append(article)
            continue
        if any(prefs.get(c, True) for c in cats):
            out.append(article)
    return out


def cluster_duplicates(articles: list[dict]) -> list[dict]:
    if not articles:
        return []

    used: set[int] = set()
    result: list[dict] = []

    for i, article in enumerate(articles):
        if i in used:
            continue
        group = [article]
        fp_i = title_fingerprint(article.get("title", ""))
        title_i = article.get("title", "").lower()

        for j in range(i + 1, len(articles)):
            if j in used:
                continue
            other = articles[j]
            fp_j = title_fingerprint(other.get("title", ""))
            title_j = other.get("title", "").lower()
            match = fp_i == fp_j and fp_i
            if not match and title_i and title_j:
                match = SequenceMatcher(None, title_i, title_j).ratio() >= DEDUP_RATIO
            if match:
                group.append(other)
                used.add(j)

        used.add(i)
        group.sort(
            key=lambda a: _parse_published_at(a.get("published_at", ""))
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        if len(group) == 1:
            item = dict(group[0])
            item["type"] = "article"
            result.append(item)
        else:
            result.append(
                {
                    "type": "cluster",
                    "title": group[0].get("title", ""),
                    "articles": group,
                    "source_count": len(group),
                    "url": group[0].get("url", ""),
                    "source": group[0].get("source", ""),
                    "published_at": group[0].get("published_at", ""),
                    "description": group[0].get("description", ""),
                    "image_url": group[0].get("image_url", ""),
                    "categories": group[0].get("categories", []),
                }
            )
    return result
