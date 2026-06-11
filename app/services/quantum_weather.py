"""Legacy module — quantum ensemble removed; sources live in weather_sources."""

from __future__ import annotations

from app.services.weather_pipeline import get_weather
from app.services.weather_sources import (  # noqa: F401
    fetch_7timer,
    fetch_all_sources,
    fetch_met_norway,
    fetch_nws,
    fetch_open_meteo,
    fetch_owm,
    fetch_weatherapi,
    wmo_str,
)

__all__ = [
    "get_weather",
    "fetch_nws",
    "fetch_open_meteo",
    "fetch_met_norway",
    "fetch_7timer",
    "fetch_owm",
    "fetch_weatherapi",
    "fetch_all_sources",
    "wmo_str",
]
