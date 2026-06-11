"""Feature extraction for location-aware weather ML."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.weather_bias import load_bias_map
from app.services.weather_observations import recent_observations
from app.services.weather_verification import get_source_scores

SOURCE_ORDER = [
    "NWS",
    "Open-Meteo",
    "MET Norway",
    "7Timer",
    "OpenWeatherMap",
    "WeatherAPI.com",
]


def _source_temp_map(sources: list[dict]) -> dict[str, float]:
    return {s["source"]: float(s["temp_f"]) for s in sources if "temp_f" in s}


def extract_features(
    sources: list[dict],
    location_id: int,
    lat: float,
    lon: float,
) -> dict[str, float]:
    temps = _source_temp_map(sources)
    bias_map = load_bias_map(location_id)
    scores = get_source_scores(location_id)
    now = datetime.now(timezone.utc)

    features: dict[str, float] = {}
    for name in SOURCE_ORDER:
        key = name.lower().replace("-", "_").replace(".", "").replace(" ", "_")
        features[f"src_{key}_temp"] = temps.get(name, 0.0)
        features[f"src_{key}_bias"] = float(
            bias_map.get(name, {}).get("temp_f", 0.0)
        )
        features[f"src_{key}_score"] = scores.get(name, 1.0)

    om = next((s for s in sources if s["source"] == "Open-Meteo"), sources[0] if sources else {})
    features["humidity"] = float(om.get("humidity") or 60)
    features["pressure_hpa"] = float(om.get("pressure_hpa") or 1013)
    features["wind_mph"] = float(om.get("wind_mph") or 0)
    features["hour_of_day"] = float(now.hour)
    features["day_of_year"] = float(now.timetuple().tm_yday)
    features["lat"] = float(lat)
    features["lon"] = float(lon)

    obs = recent_observations(location_id, hours=24)
    if len(obs) >= 2 and obs[0].get("temp_f") is not None and obs[-1].get("temp_f") is not None:
        features["obs_trend_24h"] = float(obs[0]["temp_f"]) - float(obs[-1]["temp_f"])
    else:
        features["obs_trend_24h"] = 0.0

    return features


def feature_vector(features: dict[str, float]) -> list[float]:
    keys = sorted(features.keys())
    return [features[k] for k in keys]


def feature_names() -> list[str]:
    dummy = extract_features([], 0, 0.0, 0.0)
    return sorted(dummy.keys())
