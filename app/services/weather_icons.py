def summary_to_icon_key(summary: str) -> str:
    s = (summary or "").lower()
    if "thunder" in s or "storm" in s:
        return "thunderstorm"
    if "snow" in s:
        return "snow"
    if "fog" in s:
        return "fog"
    if "shower" in s:
        return "showers"
    if "drizzle" in s:
        return "drizzle"
    if "heavy rain" in s or "rain" in s:
        return "rain"
    if "overcast" in s or "cloudy" in s:
        return "cloudy"
    if "partly" in s:
        return "partly_cloudy"
    if "clear" in s or "sunny" in s:
        return "clear"
    return "unknown"


def wmo_to_icon_key(code: int | None) -> str:
    if code is None:
        return "unknown"
    mapping = {
        0: "clear",
        1: "clear",
        2: "partly_cloudy",
        3: "cloudy",
        45: "fog",
        48: "fog",
        51: "drizzle",
        53: "drizzle",
        61: "rain",
        63: "rain",
        65: "rain",
        71: "snow",
        73: "snow",
        80: "showers",
        95: "thunderstorm",
    }
    return mapping.get(code, "unknown")
