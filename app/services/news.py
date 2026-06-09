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


def _locale_for_label(label: str) -> str | None:
    key = label.strip().lower()
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]
    if len(key) == 2 and key.isalpha():
        return key
    return None


async def fetch_news_for_location(label: str, api_token: str, limit: int = 6) -> list[dict]:
    if not api_token:
        return []
    params: dict = {"api_token": api_token, "limit": limit}
    locale = _locale_for_label(label)
    if locale:
        params["locale"] = locale
    else:
        params["search"] = label.strip()

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            "https://api.thenewsapi.com/v1/news/top",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    articles = []
    for item in data.get("data", [])[:limit]:
        articles.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "published_at": item.get("published_at", ""),
            "description": item.get("description") or item.get("snippet") or "",
            "image_url": item.get("image_url") or "",
        })
    return articles
