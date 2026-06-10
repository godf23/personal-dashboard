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
DEFAULT_LIMIT = 12
FETCH_MULTIPLIER = 4

# Drop pure weather-forecast outlets from news columns
WEATHER_NEWS_SOURCES = (
    "weather.com",
    "accuweather.com",
    "wunderground.com",
    "weather.gov",
    "theweather.com",
    "weatherbug.com",
    "weather.gov",
    "forecast.weather",
)

QUOTA_HINTS = (
    "limit",
    "quota",
    "exceeded",
    "usage",
    "rate",
    "plan allows",
    "maximum number",
    "out of",
    "not enough",
    "credits",
)


class NewsRateLimitError(Exception):
    """API key hit quota / rate limit."""


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


def _is_quota_error(status_code: int, body: str) -> bool:
    if status_code in (402, 429):
        return True
    text = (body or "").lower()
    return any(hint in text for hint in QUOTA_HINTS)


def _is_weather_news(item: dict) -> bool:
    source = (item.get("source") or "").lower()
    title = (item.get("title") or "").lower()
    if any(src in source for src in WEATHER_NEWS_SOURCES):
        return True
    if title.startswith(("weather forecast", "today's weather", "your weather")):
        return True
    return False


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
        if _is_weather_news(article):
            continue
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


async def _fetch_with_token(label: str, api_token: str, limit: int) -> list[dict]:
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
        if _is_quota_error(resp.status_code, resp.text):
            raise NewsRateLimitError(resp.text[:200] or f"HTTP {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()

    raw_articles = [_normalize_article(item) for item in data.get("data", [])]
    return _filter_recent_articles(raw_articles, limit=limit)


async def fetch_news_for_location(
    label: str,
    api_tokens: list[str],
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[dict], int | None]:
    """Try each token in order; return articles and index of token used (if any)."""
    if not api_tokens:
        return [], None

    last_error: Exception | None = None
    for index, token in enumerate(api_tokens):
        try:
            articles = await _fetch_with_token(label, token, limit)
            return articles, index
        except NewsRateLimitError as exc:
            last_error = exc
            continue
        except httpx.HTTPStatusError as exc:
            if _is_quota_error(exc.response.status_code, exc.response.text):
                last_error = NewsRateLimitError(exc.response.text[:200])
                continue
            raise

    if last_error:
        raise last_error
    return [], None
