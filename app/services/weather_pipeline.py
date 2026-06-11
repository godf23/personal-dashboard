"""Location-aware weather pipeline: fetch, bias-correct, aggregate, return."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.weather_bias import apply_bias_to_sources
from app.services.weather_ensemble import aggregate_sources, classical_weighted_mean
from app.services.weather_features import extract_features
from app.services.weather_kalman import apply_kalman, kalman_uncertainty
from app.services.weather_ml import model_available, predict_temp_quantiles
from app.services.weather_observations import get_nearest_station, observation_days
from app.services.weather_sources import (
    best_summary,
    fetch_all_sources,
    icon_key_for_summary,
    valid_sources,
)
from app.services.weather_stages import days_until_upgrade, get_pipeline_stage
from app.services.weather_verification import get_source_scores


def get_weather(
    location_id: int,
    lat: float,
    lon: float,
    owm_key: str = "",
    wapi_key: str = "",
) -> dict | None:
    sources_raw = fetch_all_sources(lat, lon, owm_key, wapi_key)
    valid = valid_sources(sources_raw)
    if not valid:
        return None

    stage = get_pipeline_stage(location_id)
    obs_days = observation_days(location_id)
    station = get_nearest_station(lat, lon)
    source_scores = get_source_scores(location_id)

    working = valid
    bias_corrected = False
    bias_snapshot: dict = {}
    if stage in ("bias", "xgboost", "kalman"):
        working, bias_corrected, bias_snapshot = apply_bias_to_sources(valid, location_id)

    classical_temp = classical_weighted_mean(working, source_scores)
    agg = aggregate_sources(working, source_scores)
    temp_f = agg["temp_f"]
    humidity = agg["humidity"]
    rain_chance = agg["rain_chance"]
    uncertainty = agg["uncertainty_f"]
    confidence_level = 0.9
    ml_quantiles: dict[str, float] | None = None

    if stage in ("xgboost", "kalman"):
        features = extract_features(working, location_id, lat, lon)
        if model_available(location_id):
            ml_quantiles = predict_temp_quantiles(location_id, features)
            if ml_quantiles:
                temp_f = ml_quantiles.get("0.5", temp_f)
                low = ml_quantiles.get("0.1")
                high = ml_quantiles.get("0.9")
                if low is not None and high is not None:
                    uncertainty = (high - low) / 2.0
                    confidence_level = 0.9

    results = {
        "temp_f": temp_f,
        "humidity": humidity,
        "rain_chance": rain_chance,
        "uncertainty_f": uncertainty,
    }

    if stage == "kalman":
        results = apply_kalman(
            location_id,
            {
                "temp_f": results["temp_f"],
                "humidity_pct": results["humidity"],
                "rain_chance_pct": results["rain_chance"],
            },
        )
        temp_f = results["temp_f"]
        humidity = results.get("humidity_pct", humidity)
        rain_chance = results.get("rain_chance_pct", rain_chance)
        k_unc = kalman_uncertainty(location_id)
        if k_unc is not None:
            uncertainty = k_unc

    summary = best_summary(valid)
    om = next((s for s in valid if s["source"] == "Open-Meteo"), None)
    wind = next((s.get("wind_mph") for s in valid if s.get("wind_mph") is not None), None)
    feels = next((s.get("feels_like") for s in valid if s.get("feels_like") is not None), None)

    return {
        "temperature_f": round(temp_f, 1),
        "uncertainty_f": round(uncertainty, 2),
        "confidence_level": confidence_level,
        "classical_temp_f": round(classical_temp, 1),
        "humidity_pct": round(humidity),
        "rain_chance_pct": round(rain_chance),
        "summary": summary,
        "icon_key": icon_key_for_summary(summary),
        "feels_like_f": round(feels, 1) if feels is not None else None,
        "wind_mph": wind,
        "pressure_hpa": om.get("pressure_hpa") if om else None,
        "cloud_cover_pct": om.get("cloud_cover") if om else None,
        "dew_point_f": om.get("dew_point_f") if om else None,
        "uv_index": om.get("uv_index") if om else None,
        "active_sources": len(valid),
        "total_sources": 6,
        "pipeline_stage": stage,
        "bias_corrected": bias_corrected,
        "observation_station": station["id"],
        "observation_days": obs_days,
        "days_until_upgrade": days_until_upgrade(obs_days, stage),
        "source_scores": source_scores,
        "bias_snapshot": bias_snapshot,
        "ml_quantiles": ml_quantiles,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
