import asyncio
import time
from functools import partial

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.database import _utcnow, get_db
from app.services.geocoding import geocode_location
from app.services.forecast import fetch_weather_bundle
from app.services.quantum_weather import get_weather

router = APIRouter(prefix="/api/weather", tags=["weather"])

_cache: dict[int, tuple[float, dict]] = {}
CACHE_TTL = 600


class LocationCreate(BaseModel):
    label: str


def _get_locations():
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM weather_locations ORDER BY sort_order, id"
        ).fetchall()


@router.get("/locations")
def list_weather_locations():
    rows = _get_locations()
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "lat": r["lat"],
            "lon": r["lon"],
            "sort_order": r["sort_order"],
        }
        for r in rows
    ]


@router.post("/locations")
async def add_weather_location(body: LocationCreate):
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "Label is required")
    geo = await geocode_location(label)
    if not geo:
        raise HTTPException(400, f"Could not geocode: {label}")
    lat, lon, resolved = geo
    with get_db() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) FROM weather_locations"
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO weather_locations (label, lat, lon, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (resolved, lat, lon, max_order + 1, _utcnow()),
        )
        row = conn.execute(
            "SELECT * FROM weather_locations WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return {
        "id": row["id"],
        "label": row["label"],
        "lat": row["lat"],
        "lon": row["lon"],
        "sort_order": row["sort_order"],
    }


@router.delete("/locations/{location_id}")
def delete_weather_location(location_id: int):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM weather_locations WHERE id = ?", (location_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Location not found")
    _cache.pop(location_id, None)
    return {"ok": True}


def _fetch_weather_sync(lat: float, lon: float, owm: str, wapi: str) -> dict | None:
    return get_weather(lat, lon, owm, wapi)


@router.get("")
async def get_all_weather():
    settings = get_settings()
    rows = _get_locations()
    results = []
    now = time.time()

    async def process_row(row):
        loc_id = row["id"]
        if loc_id in _cache:
            cached_at, data = _cache[loc_id]
            if now - cached_at < CACHE_TTL:
                lat, lon = row["lat"], row["lon"]
                if lat is not None and lon is not None and not data.get("forecast_7day"):
                    bundle = await fetch_weather_bundle(lat, lon)
                    data = {**data, **bundle}
                    _cache[loc_id] = (cached_at, data)
                return {**data, "id": loc_id, "location": row["label"], "cached": True}

        lat, lon = row["lat"], row["lon"]
        if lat is None or lon is None:
            geo = await geocode_location(row["label"])
            if not geo:
                return {
                    "id": loc_id,
                    "location": row["label"],
                    "error": "Geocoding failed",
                }
            lat, lon, resolved = geo
            with get_db() as conn:
                conn.execute(
                    "UPDATE weather_locations SET lat = ?, lon = ?, label = ? WHERE id = ?",
                    (lat, lon, resolved, loc_id),
                )

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            partial(_fetch_weather_sync, lat, lon, settings.owm_api_key, settings.wapi_api_key),
        )
        if not data:
            return {
                "id": loc_id,
                "location": row["label"],
                "lat": lat,
                "lon": lon,
                "error": "No valid weather sources",
            }
        bundle = await fetch_weather_bundle(lat, lon)
        payload = {
            **data,
            **bundle,
            "id": loc_id,
            "location": row["label"],
            "lat": lat,
            "lon": lon,
            "cached": False,
        }
        _cache[loc_id] = (now, payload)
        return payload

    if rows:
        tasks = [process_row(r) for r in rows]
        results = await asyncio.gather(*tasks)
    return results
