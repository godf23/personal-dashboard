"""Weekly per-source accuracy scoring and dynamic down-weighting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import _utcnow, get_db

BAD_DAY_THRESHOLD_F = 5.0
MIN_SCORE = 0.1


def _week_start() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()


def recompute_scores_for_location(location_id: int) -> int:
    start = _week_start()
    now = _utcnow()
    updated = 0

    with get_db() as conn:
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
                """
                SELECT p.temp_f AS predicted, o.temp_f AS observed, p.logged_at
                FROM weather_predictions_log p
                JOIN weather_observations o
                  ON o.location_id = p.location_id
                 AND substr(o.observed_at, 1, 13) = substr(p.logged_at, 1, 13)
                WHERE p.location_id = ?
                  AND p.source_name = ?
                  AND p.logged_at >= ?
                  AND p.temp_f IS NOT NULL
                  AND o.temp_f IS NOT NULL
                ORDER BY p.logged_at
                """,
                (location_id, source_name, start),
            ).fetchall()

            if not pairs:
                continue

            errors = [abs(float(r["predicted"]) - float(r["observed"])) for r in pairs]
            mae = sum(errors) / len(errors)
            score = max(MIN_SCORE, min(1.0, 1.0 - mae / 10.0))

            prev = conn.execute(
                """
                SELECT bad_streak FROM weather_source_scores
                WHERE location_id = ? AND source_name = ?
                """,
                (location_id, source_name),
            ).fetchone()
            bad_streak = int(prev["bad_streak"]) if prev else 0

            daily: dict[str, list[float]] = {}
            for r in pairs:
                day = str(r["logged_at"])[:10]
                daily.setdefault(day, []).append(
                    abs(float(r["predicted"]) - float(r["observed"]))
                )
            if daily:
                last_day = max(daily.keys())
                day_mae = sum(daily[last_day]) / len(daily[last_day])
                if day_mae > BAD_DAY_THRESHOLD_F:
                    bad_streak += 1
                else:
                    bad_streak = max(0, bad_streak - 1)

            if bad_streak >= 7:
                score = max(MIN_SCORE, score * 0.5)
                bad_streak = 0

            conn.execute(
                """
                INSERT INTO weather_source_scores (
                    location_id, source_name, mae_temp, score, bad_streak, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(location_id, source_name) DO UPDATE SET
                    mae_temp = excluded.mae_temp,
                    score = excluded.score,
                    bad_streak = excluded.bad_streak,
                    updated_at = excluded.updated_at
                """,
                (location_id, source_name, mae, score, bad_streak, now),
            )
            updated += 1
    return updated


def recompute_scores_all_locations() -> dict[int, int]:
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM weather_locations").fetchall()
    return {r["id"]: recompute_scores_for_location(r["id"]) for r in rows}


def get_source_scores(location_id: int) -> dict[str, float]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT source_name, score FROM weather_source_scores
            WHERE location_id = ?
            """,
            (location_id,),
        ).fetchall()
    return {r["source_name"]: float(r["score"]) for r in rows}


def get_source_scores_detail(location_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT source_name, mae_temp, score, bad_streak, updated_at
            FROM weather_source_scores
            WHERE location_id = ?
            ORDER BY score DESC
            """,
            (location_id,),
        ).fetchall()
    return [dict(r) for r in rows]
