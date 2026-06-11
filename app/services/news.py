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
FREE_TIER_FALLBACK_LIMIT = 3

WEATHER_NEWS_SOURCES = (
    "weather.com",
    "accuweather.com",
    "wunderground.com",
    "weather.gov",
    "theweather.com",
    "weatherbug.com",
    "forecast.weather",
)

# The News API returns HTTP 200 with a warnings[] array when a key/plan is capped.
PLAN_LIMIT_PHRASES = (
    "limit is higher than your plan allows",
    "higher than your plan allows",
    "plan allows",
)

TOKEN_EXHAUSTED_PHRASES = (
    "api token",
    "request allowance",
    "requests remaining",
    "quota",
    "exceeded your",
    "out of requests",
    "no requests",
    "not authorized",
    "invalid api token",
)


class NewsRateLimitError(Exception):
    """API key exhausted — rotate to the next backup key."""


class NewsPlanLimitError(Exception):
    """Requested limit exceeds plan; includes the plan cap from meta.limit."""

    def __init__(self, message: str, plan_cap: int):
        super().__init__(message)
        self.plan_cap = plan_cap


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


def _warning_texts(data: dict) -> list[str]:
    return [str(w) for w in (data.get("warnings") or [])]


def _is_plan_limit_warning(warnings: list[str]) -> bool:
    blob = " ".join(warnings).lower()
    return any(phrase in blob for phrase in PLAN_LIMIT_PHRASES)


def _is_token_exhausted_warning(warnings: list[str]) -> bool:
    blob = " ".join(warnings).lower()
    if _is_plan_limit_warning(warnings):
        return False
    return any(phrase in blob for phrase in TOKEN_EXHAUSTED_PHRASES)


def _plan_cap_from_meta(data: dict, requested: int) -> int:
    meta = data.get("meta") or {}
    cap = meta.get("limit")
    try:
        if cap is not None:
            return max(1, int(cap))
    except (TypeError, ValueError):
        pass
    return min(requested, FREE_TIER_FALLBACK_LIMIT)


def _analyze_response(data: dict, status_code: int, raw_text: str) -> None:
    """Raise when the API signals plan cap or key exhaustion."""
    if status_code in (402, 429):
        raise NewsRateLimitError(raw_text[:300] or f"HTTP {status_code}")

    warnings = _warning_texts(data)
    if not warnings:
        return

    if _is_plan_limit_warning(warnings):
        cap = _plan_cap_from_meta(data, DEFAULT_LIMIT)
        msg = "; ".join(warnings)
        raise NewsPlanLimitError(msg, cap)

    if _is_token_exhausted_warning(warnings) or not data.get("data"):
        raise NewsRateLimitError("; ".join(warnings))


def _is_weather_news(item: dict) -> bool:
    source = (item.get("source") or "").lower()
    title = (item.get("title") or "").lower()
    if any(src in source for src in WEATHER_NEWS_SOURCES):
        return True
    if title.startswith(("weather forecast", "today's weather", "your weather")):
        return True
    return False


def _normalize_categories(item: dict) -> list[str]:
    raw = item.get("categories")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(c).strip() for c in raw if str(c).strip()]
    if isinstance(raw, str):
        return [c.strip() for c in raw.split(",") if c.strip()]
    return []


def _normalize_article(item: dict) -> dict:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source": item.get("source", ""),
        "published_at": item.get("published_at", ""),
        "description": item.get("description") or item.get("snippet") or "",
        "image_url": item.get("image_url") or "",
        "categories": _normalize_categories(item),
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


async def _fetch_with_token(
    label: str,
    api_token: str,
    limit: int,
    *,
    request_limit: int | None = None,
    days: int = RECENT_DAYS,
) -> list[dict]:
    locale = _locale_for_label(label)
    fetch_limit = request_limit or min(max(limit * FETCH_MULTIPLIER, limit), 50)
    params: dict = {
        "api_token": api_token,
        "limit": fetch_limit,
        "language": "en",
        "sort": "published_at",
        "published_after": _published_after(days),
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
        raw = resp.text
        if resp.status_code in (402, 429):
            raise NewsRateLimitError(raw[:300] or f"HTTP {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()

    _analyze_response(data, resp.status_code, raw)

    raw_articles = [_normalize_article(item) for item in data.get("data", [])]
    return _filter_recent_articles(raw_articles, limit=limit, days=days)


async def fetch_news_for_location(
    label: str,
    api_tokens: list[str],
    limit: int = DEFAULT_LIMIT,
    *,
    days: int = RECENT_DAYS,
) -> tuple[list[dict], int | None]:
    """Try each token in order; rotate on plan/key limit warnings from The News API."""
    if not api_tokens:
        return [], None

    effective_limit = limit
    last_error: Exception | None = None

    for index, token in enumerate(api_tokens):
        try:
            articles = await _fetch_with_token(label, token, effective_limit, days=days)
            return articles, index
        except NewsPlanLimitError as exc:
            last_error = exc
            effective_limit = min(effective_limit, exc.plan_cap)
            # Retry same key immediately at plan cap before rotating.
            try:
                articles = await _fetch_with_token(
                    label,
                    token,
                    effective_limit,
                    request_limit=effective_limit,
                    days=days,
                )
                return articles, index
            except (NewsPlanLimitError, NewsRateLimitError):
                continue
        except NewsRateLimitError as exc:
            last_error = exc
            continue
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (402, 429):
                last_error = NewsRateLimitError(exc.response.text[:300])
                continue
            raise

    if last_error:
        raise last_error
    return [], None
