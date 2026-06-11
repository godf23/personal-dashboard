"""Per-location pipeline stage thresholds."""

from __future__ import annotations

from app.services.weather_observations import observation_days

STAGE_ORDER = ("trimmed_mean", "bias", "xgboost", "kalman")
STAGE_THRESHOLDS = {
    "trimmed_mean": 0,
    "bias": 30,
    "xgboost": 60,
    "kalman": 180,
}


def get_pipeline_stage(location_id: int) -> str:
    days = observation_days(location_id)
    if days >= STAGE_THRESHOLDS["kalman"]:
        return "kalman"
    if days >= STAGE_THRESHOLDS["xgboost"]:
        return "xgboost"
    if days >= STAGE_THRESHOLDS["bias"]:
        return "bias"
    return "trimmed_mean"


def days_until_upgrade(obs_days: int, current_stage: str) -> int | None:
    idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else 0
    if idx >= len(STAGE_ORDER) - 1:
        return None
    next_stage = STAGE_ORDER[idx + 1]
    need = STAGE_THRESHOLDS[next_stage]
    return max(0, need - obs_days)
