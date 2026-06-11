"""30-day rolling per-source bias correction."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.database import _utcnow, get_db

BIAS_VARIABLES = {
    "temp_f": ("temp_f", "temp_f"),
    "humidity": ("humidity", "humidity_pct"),
}


def _window_start(days: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def recompute_bias_for_location(location_id: int, window_days: int = 30) -> int:
    """Recompute bias table from paired prediction/observation logs. Returns rows updated."""
    start = _window_start(window_days)
    updated = 0
    now = _utcnow()

    with get_db() as conn:
        for variable, (pred_col, obs_col) in BIAS_VARIABLES.items():
            sources = conn.execute(
                """
                SELECT DISTINCT source_name FROM weather_predictions_log
                WHERE location_id = ? AND logged_at >= ?
                """,
                (location_id, start),
            ).fetchall()

            for src_row in sources:
                source_name = src_row["source_name"]
                pairs = conn.execute(
                    f"""
                    SELECT p.{pred_col} AS predicted, o.{obs_col} AS observed
                    FROM weather_predictions_log p
                    JOIN weather_observations o
                      ON o.location_id = p.location_id
                     AND substr(o.observed_at, 1, 13) = substr(p.logged_at, 1, 13)
                    WHERE p.location_id = ?
                      AND p.source_name = ?
                      AND p.logged_at >= ?
                      AND p.{pred_col} IS NOT NULL
                      AND o.{obs_col} IS NOT NULL
                    """,
                    (location_id, source_name, start),
                ).fetchall()

                if not pairs:
                    continue

                errors = [float(r["predicted"]) - float(r["observed"]) for r in pairs]
                bias = sum(errors) / len(errors)
                conn.execute(
                    """
                    INSERT INTO weather_source_bias (
                        location_id, source_name, variable, bias_value,
                        sample_count, window_start, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(location_id, source_name, variable) DO UPDATE SET
                        bias_value = excluded.bias_value,
                        sample_count = excluded.sample_count,
                        window_start = excluded.window_start,
                        updated_at = excluded.updated_at
                    """,
                    (
                        location_id,
                        source_name,
                        variable,
                        bias,
                        len(errors),
                        start,
                        now,
                    ),
                )
                updated += 1
    return updated


def recompute_bias_all_locations() -> dict[int, int]:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM weather_locations").fetchall()
    return {r["id"]: recompute_bias_for_location(r["id"]) for r in rows}


def load_bias_map(location_id: int) -> dict[str, dict[str, float]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT source_name, variable, bias_value, sample_count
            FROM weather_source_bias
            WHERE location_id = ?
            """,
            (location_id,),
        ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["source_name"], {})[r["variable"]] = float(r["bias_value"])
    return out


def apply_bias_to_sources(sources: list[dict], location_id: int) -> tuple[list[dict], bool, dict]:
    bias_map = load_bias_map(location_id)
    if not bias_map:
        return sources, False, {}

    corrected = []
    for s in sources:
        c = copy.deepcopy(s)
        src_bias = bias_map.get(s["source"], {})
        if "temp_f" in c and "temp_f" in src_bias:
            c["temp_f"] = float(c["temp_f"]) - src_bias["temp_f"]
        if c.get("humidity") is not None and "humidity" in src_bias:
            c["humidity"] = float(c["humidity"]) - src_bias["humidity"]
        if c.get("rain_chance") is not None and "rain_chance" in src_bias:
            c["rain_chance"] = max(0.0, float(c["rain_chance"]) - src_bias["rain_chance"])
        corrected.append(c)
    return corrected, True, bias_map
