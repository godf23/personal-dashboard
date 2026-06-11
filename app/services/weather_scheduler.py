"""Hourly observation logging and weekly bias/verification jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.services.weather_bias import recompute_bias_all_locations
from app.services.weather_kalman import update_from_observation
from app.services.weather_ml import retrain_all_eligible
from app.services.weather_observations import fetch_observation, log_all_locations
from app.services.weather_stages import get_pipeline_stage
from app.services.weather_verification import recompute_scores_all_locations

log = logging.getLogger(__name__)

_last_hour: str | None = None
_last_weekly: str | None = None
_last_monthly: str | None = None


async def hourly_job() -> None:
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, log_all_locations)
        logged = sum(1 for r in results if not r.get("skipped"))
        if logged:
            log.info("Weather hourly log: %d location(s)", logged)
    except Exception:
        log.exception("Weather hourly job failed")


async def weekly_job() -> None:
    loop = asyncio.get_event_loop()
    try:
        bias = await loop.run_in_executor(None, recompute_bias_all_locations)
        scores = await loop.run_in_executor(None, recompute_scores_all_locations)
        log.info(
            "Weather weekly: bias rows=%s, score rows=%s",
            sum(bias.values()),
            sum(scores.values()),
        )
    except Exception:
        log.exception("Weather weekly job failed")


async def monthly_retrain_job() -> None:
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, retrain_all_eligible)
        trained = sum(1 for ok in results.values() if ok)
        if trained:
            log.info("Weather monthly retrain: %d model(s)", trained)
    except Exception:
        log.exception("Weather monthly retrain failed")


async def _kalman_updates_after_log() -> None:
    from app.database import get_db

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, lat, lon FROM weather_locations WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchall()
    for row in rows:
        if get_pipeline_stage(row["id"]) != "kalman":
            continue
        obs, _ = fetch_observation(row["lat"], row["lon"])
        if obs:
            update_from_observation(row["id"], obs)


async def weather_scheduler_loop() -> None:
    global _last_hour, _last_weekly, _last_monthly
    log.info("Weather scheduler started")
    while True:
        now = datetime.now(timezone.utc)
        hour_key = now.strftime("%Y-%m-%dT%H")
        week_key = now.strftime("%Y-W%W")
        month_key = now.strftime("%Y-%m")

        if hour_key != _last_hour:
            _last_hour = hour_key
            await hourly_job()
            await _kalman_updates_after_log()

        if now.weekday() == 6 and now.hour == 3 and week_key != _last_weekly:
            _last_weekly = week_key
            await weekly_job()

        if now.day == 1 and now.hour == 2 and month_key != _last_monthly:
            _last_monthly = month_key
            await monthly_retrain_job()

        await asyncio.sleep(60)


def start_weather_scheduler() -> asyncio.Task:
    return asyncio.create_task(weather_scheduler_loop())
