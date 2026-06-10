from datetime import datetime, timedelta, timezone

import httpx

COUNTRY_MAP = {
    "us": "us",
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
    "uk": "gb",
    "united kingdom": "gb",
    "great britain": "gb",
    "canada": "ca",
    "australia": "au",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "japan": "jp",
    "india": "in",
    "mexico": "mx",
    "brazil": "br",
}

RECENT_DAYS = 7
FETCH_MULTIPLIER = 4


def _locale_for_label(label: str) -> str | None:
    key = label.strip().lower()
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]
    if len(key) == 2 and key.isalpha():
        return key
    return None


def _published_after(days: int = RECENT_DAYS) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%d")


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


def _normalize_article(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source": item.get("source", ""),
        "published_at": item.get("published_at", ""),
        "description": item.get("description") or item.get("snippet") or "",
        "image_url": item.get("image_url") or "",
    }


def _filter_recent_articles(articles: list[dict], *, limit: int, days: int = RECENT_DAYS) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for article in articles:
        published = _parse_published_at(article.get("published_at", ""))
        if published is None or published < cutoff:
            continue
        recent.append(article)

    recent.sort(
        key=lambda article: _parse_published_at(article.get("published_at", ""))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return recent[:limit]


async def fetch_news_for_location(label: str, api_token: str, limit: int = 6) -> list[dict]:
    if not api_token:
        return []

    locale = _locale_for_label(label)
    fetch_limit = min(max(limit * FETCH_MULTIPLIER, limit), 50)
    params: dict = {
        "api_token": api_token,
        "limit": fetch_limit,
        "language": "en",
        "sort": "published_at",
        "published_after": _published_after(),
    }
    if locale:
        params["locale"] = locale
    else:
        params["search"] = label.strip()
        params["search_fields"] = "title,description,keywords"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            "https://api.thenewsapi.com/v1/news/top",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    raw_articles = [_normalize_article(item) for item in data.get("data", [])]
    return _filter_recent_articles(raw_articles, limit=limit)
