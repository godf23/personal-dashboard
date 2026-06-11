"""Ground-truth observations and prediction logging."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from app.config import BASE_DIR, get_settings
from app.database import _utcnow, get_db
from app.services.weather_sources import fetch_all_sources

STATIONS_PATH = BASE_DIR / "app" / "data" / "weather_stations.json"
UA = "PersonalDashboard/1.0 (weather-obs)"

_stations_cache: list[dict] | None = None


def load_stations() -> list[dict]:
    global _stations_cache
    if _stations_cache is None:
        with open(STATIONS_PATH, encoding="utf-8") as f:
            _stations_cache = json.load(f)
    return _stations_cache


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_nearest_station(lat: float, lon: float) -> dict:
    stations = load_stations()
    pws = [s for s in stations if s.get("type") == "PWS"]
    metar = [s for s in stations if s.get("type") == "METAR"]
    if pws:
        nearest_pws = min(pws, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))
        if haversine_km(lat, lon, nearest_pws["lat"], nearest_pws["lon"]) <= 80:
            return nearest_pws
    pool = metar or stations
    return min(pool, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))


def _fetch_metar(station_id: str) -> dict | None:
    try:
        r = requests.get(
            "https://aviationweather.gov/api/data/metar",
            params={"ids": station_id, "format": "json"},
            headers={"User-Agent": UA},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        m = data[0]
        temp_c = m.get("temp")
        if temp_c is None:
            return None
        temp_f = temp_c * 9 / 5 + 32
        dewp_c = m.get("dewp")
        humidity = None
        if dewp_c is not None and temp_c != dewp_c:
            try:
                humidity = min(
                    100,
                    max(
                        0,
                        100
                        - 5
                        * (
                            (112 - (20.4 + temp_c)) * (temp_c - dewp_c)
                            / (112 + temp_c)
                        ),
                    ),
                )
            except (ZeroDivisionError, TypeError):
                humidity = None
        wspd_kt = m.get("wspd")
        wind_mph = wspd_kt * 1.15078 if wspd_kt is not None else None
        return {
            "temp_f": float(temp_f),
            "humidity_pct": round(humidity) if humidity is not None else None,
            "rain_mm": 0.0,
            "source_type": "METAR",
        }
    except Exception:
        return None


def _fetch_pws_wu(station_id: str, api_key: str) -> dict | None:
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://api.weather.com/v2/pws/observations/current",
            params={
                "stationId": station_id,
                "format": "json",
                "units": "e",
                "apiKey": api_key,
            },
            timeout=12,
        )
        r.raise_for_status()
        obs = r.json().get("observations", [{}])[0]
        if not obs:
            return None
        temp_f = obs.get("imperial", {}).get("temp")
        if temp_f is None:
            return None
        humidity = obs.get("humidity")
        rain_mm = obs.get("metric", {}).get("precipTotal") or 0.0
        return {
            "temp_f": float(temp_f),
            "humidity_pct": float(humidity) if humidity is not None else None,
            "rain_mm": float(rain_mm),
            "source_type": "PWS",
        }
    except Exception:
        return None


def _fetch_open_meteo_current(lat: float, lon: float) -> dict | None:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation"
            f"&temperature_unit=fahrenheit"
        )
        d = requests.get(url, timeout=10).json()["current"]
        return {
            "temp_f": float(d["temperature_2m"]),
            "humidity_pct": d.get("relative_humidity_2m"),
            "rain_mm": float(d.get("precipitation") or 0),
            "source_type": "Open-Meteo",
        }
    except Exception:
        return None


def fetch_observation(lat: float, lon: float, station: dict | None = None) -> tuple[dict | None, dict]:
    """Return (observation dict, station used)."""
    station = station or get_nearest_station(lat, lon)
    settings = get_settings()
    obs = None

    if station.get("type") == "PWS":
        obs = _fetch_pws_wu(station["id"], settings.pws_api_key)
    if obs is None:
        obs = _fetch_metar(station["id"])
    if obs is None and station.get("fallback"):
        fallback = next((s for s in load_stations() if s["id"] == station["fallback"]), None)
        if fallback:
            obs = _fetch_metar(fallback["id"])
            if obs:
                station = fallback
    if obs is None:
        obs = _fetch_open_meteo_current(lat, lon)
    return obs, station


def observation_days(location_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT substr(observed_at, 1, 10)) AS days
            FROM weather_observations
            WHERE location_id = ? AND temp_f IS NOT NULL
            """,
            (location_id,),
        ).fetchone()
    return int(row["days"] or 0)


def observation_count(location_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM weather_observations WHERE location_id = ?",
            (location_id,),
        ).fetchone()
    return int(row["n"] or 0)


def _hour_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H")


def already_logged_this_hour(location_id: int, dt: datetime | None = None) -> bool:
    hour = _hour_key(dt)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM weather_predictions_log
            WHERE location_id = ? AND logged_at LIKE ?
            LIMIT 1
            """,
            (location_id, f"{hour}%"),
        ).fetchone()
    return row is not None


def log_predictions(location_id: int, sources: list[dict], logged_at: str | None = None) -> None:
    ts = logged_at or _utcnow()
    with get_db() as conn:
        for s in sources:
            if s.get("skipped") or s.get("error") or "temp_f" not in s:
                continue
            conn.execute(
                """
                INSERT INTO weather_predictions_log (
                    location_id, logged_at, source_name, temp_f, humidity_pct,
                    rain_chance_pct, pressure_hpa, wind_mph, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_id,
                    ts,
                    s["source"],
                    s.get("temp_f"),
                    s.get("humidity"),
                    s.get("rain_chance"),
                    s.get("pressure_hpa"),
                    s.get("wind_mph"),
                    json.dumps(s, default=str),
                ),
            )


def log_observation(
    location_id: int,
    station_id: str,
    obs: dict,
    observed_at: str | None = None,
) -> None:
    ts = observed_at or _utcnow()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO weather_observations (
                location_id, station_id, observed_at, temp_f,
                humidity_pct, rain_mm, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                location_id,
                station_id,
                ts,
                obs.get("temp_f"),
                obs.get("humidity_pct"),
                obs.get("rain_mm"),
                obs.get("source_type", "unknown"),
            ),
        )


def log_hourly_for_location(
    location_id: int,
    lat: float,
    lon: float,
    owm_key: str = "",
    wapi_key: str = "",
) -> dict:
    """Fetch sources + observation and log both. Skips if already logged this hour."""
    if already_logged_this_hour(location_id):
        return {"skipped": True, "location_id": location_id}

    sources = fetch_all_sources(lat, lon, owm_key, wapi_key)
    ts = _utcnow()
    log_predictions(location_id, sources, ts)

    obs, station = fetch_observation(lat, lon)
    if obs:
        log_observation(location_id, station["id"], obs, ts)

    return {
        "location_id": location_id,
        "station_id": station["id"],
        "obs_logged": obs is not None,
        "sources_logged": sum(
            1 for s in sources if "temp_f" in s and not s.get("skipped") and not s.get("error")
        ),
    }


def log_all_locations() -> list[dict]:
    settings = get_settings()
    results = []
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, lat, lon FROM weather_locations WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchall()
    for row in rows:
        results.append(
            log_hourly_for_location(
                row["id"],
                row["lat"],
                row["lon"],
                settings.owm_api_key,
                settings.wapi_api_key,
            )
        )
    return results


def recent_observations(location_id: int, hours: int = 24) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM weather_observations
            WHERE location_id = ? AND observed_at >= ?
            ORDER BY observed_at DESC
            """,
            (location_id, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


def pipeline_stats(location_id: int) -> dict:
    from app.services.weather_stages import days_until_upgrade, get_pipeline_stage

    station = None
    with get_db() as conn:
        loc = conn.execute(
            "SELECT lat, lon, label FROM weather_locations WHERE id = ?",
            (location_id,),
        ).fetchone()
    if loc and loc["lat"] is not None:
        station = get_nearest_station(loc["lat"], loc["lon"])

    stage = get_pipeline_stage(location_id)
    days = observation_days(location_id)
    return {
        "location_id": location_id,
        "label": loc["label"] if loc else None,
        "observation_days": days,
        "observation_count": observation_count(location_id),
        "pipeline_stage": stage,
        "days_until_upgrade": days_until_upgrade(days, stage),
        "nearest_station": station["id"] if station else None,
    }


def all_pipeline_stats() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM weather_locations ORDER BY sort_order, id").fetchall()
    return [pipeline_stats(r["id"]) for r in rows]
