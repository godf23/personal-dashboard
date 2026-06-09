from datetime import datetime

import httpx

from app.services.weather_icons import wmo_to_icon_key


async def fetch_7day_forecast(lat: float, lon: float) -> list[dict]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    daily = data.get("daily", {})
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
