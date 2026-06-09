import httpx

STATE_ABBR = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "fl": "Florida", "ga": "Georgia", "hi": "Hawaii", "id": "Idaho",
    "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "ri": "Rhode Island", "sc": "South Carolina",
    "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas", "ut": "Utah",
    "vt": "Vermont", "va": "Virginia", "wa": "Washington", "wv": "West Virginia",
    "wi": "Wisconsin", "wy": "Wyoming", "dc": "District of Columbia",
}


def _search_variants(label: str) -> list[str]:
    label = label.strip()
    variants = [label]
    if "," in label:
        parts = [p.strip() for p in label.split(",") if p.strip()]
        if parts:
            variants.append(parts[0])
        if len(parts) >= 2:
            state = parts[1].lower()
            if state in STATE_ABBR:
                variants.append(f"{parts[0]}, {STATE_ABBR[state]}")
            variants.append(", ".join(parts))
    seen = set()
    ordered = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


async def _geocode_query(query: str) -> tuple[float, float, str] | None:
    url = "https://geocoding-api.open-meteo.com/v1/search"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"name": query, "count": 1, "language": "en"})
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    name = r.get("name", query)
    admin = r.get("admin1", "")
    country = r.get("country", "")
    parts = [name]
    if admin:
        parts.append(admin)
    if country:
        parts.append(country)
    resolved = ", ".join(parts)
    return float(r["latitude"]), float(r["longitude"]), resolved


async def geocode_location(label: str) -> tuple[float, float, str] | None:
    label = label.strip()
    if not label:
        return None
    for variant in _search_variants(label):
        result = await _geocode_query(variant)
        if result:
            return result
    return None
