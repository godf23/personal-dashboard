import re

import httpx

_OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_IMAGE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)
_OG_DESC = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)

_preview_cache: dict[str, dict] = {}


async def fetch_page_preview(url: str) -> dict:
    if url in _preview_cache:
        return _preview_cache[url]
    result = {"image_url": "", "description": ""}
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers={"User-Agent": "DashboardPreview/1.0"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text[:50000]
        for pat in (_OG_IMAGE, _OG_IMAGE_ALT):
            m = pat.search(html)
            if m:
                result["image_url"] = m.group(1)
                break
        for pat in (_OG_DESC, _META_DESC):
            m = pat.search(html)
            if m:
                result["description"] = m.group(1)[:300]
                break
    except Exception:
        pass
    _preview_cache[url] = result
    return result
