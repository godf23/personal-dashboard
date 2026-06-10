from datetime import datetime

import httpx

from app.services.weather_icons import wmo_to_icon_key


def _format_local_time(iso_str: str) -> str | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        hour = dt.strftime("%I").lstrip("0") or "12"
        return f"{hour}:{dt.strftime('%M %p')}"
    except ValueError:
        return None


def _pollen_level(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 10:
        return "Low"
    if value < 50:
        return "Moderate"
    if value < 100:
        return "High"
    return "Very High"


def _build_forecast(daily: dict) -> list[dict]:
    times = daily.get("time", [])
    forecast = []
    for i, day_str in enumerate(times):
        code = daily.get("weather_code", [None] * len(times))[i]
        hi = daily.get("temperature_2m_max", [None] * len(times))[i]
        lo = daily.get("temperature_2m_min", [None] * len(times))[i]
        rain = daily.get("precipitation_probability_max", [0] * len(times))[i]
        dt = datetime.fromisoformat(day_str)
        forecast.append({
            "date": day_str,
            "day": dt.strftime("%a"),
            "high_f": round(float(hi)) if hi is not None else None,
            "low_f": round(float(lo)) if lo is not None else None,
            "rain_chance_pct": int(rain or 0),
            "icon_key": wmo_to_icon_key(code),
        })
    return forecast


async def _fetch_pollen(lat: float, lon: float) -> dict:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "grass_pollen,tree_pollen,weed_pollen",
        "timezone": "auto",
        "forecast_days": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return {
            "grass_pollen": None,
            "tree_pollen": None,
            "weed_pollen": None,
            "pollen_summary": None,
        }

    hourly = data.get("hourly", {})
    grass = hourly.get("grass_pollen", [])
    tree = hourly.get("tree_pollen", [])
    weed = hourly.get("weed_pollen", [])

    def _max_val(values: list) -> float | None:
        nums = [float(v) for v in values if v is not None]
        return max(nums) if nums else None

    g = _max_val(grass)
    t = _max_val(tree)
    w = _max_val(weed)
    levels = [_pollen_level(v) for v in (g, t, w) if v is not None]
    summary = None
    if levels:
        rank = {"Low": 1, "Moderate": 2, "High": 3, "Very High": 4}
        summary = max(levels, key=lambda lv: rank.get(lv, 0))

    return {
        "grass_pollen": round(g, 1) if g is not None else None,
        "tree_pollen": round(t, 1) if t is not None else None,
        "weed_pollen": round(w, 1) if w is not None else None,
        "pollen_summary": summary,
    }


async def fetch_weather_bundle(lat: float, lon: float) -> dict:
    """7-day forecast plus extended current conditions for detail view."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "precipitation_probability,weather_code,wind_speed_10m,wind_direction_10m,"
            "surface_pressure,cloud_cover,dew_point_2m,uv_index"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,sunrise,sunset,uv_index_max"
        ),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    daily = data.get("daily", {})
    current = data.get("current", {})
    forecast = _build_forecast(daily)
    sunrises = daily.get("sunrise", [])
    sunsets = daily.get("sunset", [])
    pollen = await _fetch_pollen(lat, lon)

    wind_dir = current.get("wind_direction_10m")
    wind_label = f"{round(wind_dir)}°" if wind_dir is not None else None

    return {
        "forecast_7day": forecast,
        "feels_like_f": round(float(current["apparent_temperature"]), 1)
        if current.get("apparent_temperature") is not None
        else None,
        "sunrise": _format_local_time(sunrises[0]) if sunrises else None,
        "sunset": _format_local_time(sunsets[0]) if sunsets else None,
        "uv_index_max": round(float(daily["uv_index_max"][0]), 1)
        if daily.get("uv_index_max")
        else None,
        "wind_direction": wind_label,
        **pollen,
    }


async def fetch_7day_forecast(lat: float, lon: float) -> list[dict]:
    bundle = await fetch_weather_bundle(lat, lon)
    return bundle.get("forecast_7day", [])
