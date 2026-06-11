"""Kalman filters for temp, humidity, and rain chance."""

from __future__ import annotations

from app.database import _utcnow, get_db

KALMAN_VARS = ("temp_f", "humidity_pct", "rain_chance_pct")
PROCESS_NOISE = 0.05
MEASUREMENT_NOISE = 1.5


class KalmanFilter1D:
    def __init__(
        self,
        estimate: float = 0.0,
        error_cov: float = 1.0,
        process_noise: float = PROCESS_NOISE,
        measurement_noise: float = MEASUREMENT_NOISE,
    ):
        self.estimate = estimate
        self.error_cov = error_cov
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

    def predict(self) -> float:
        self.error_cov += self.process_noise
        return self.estimate

    def update(self, measurement: float) -> float:
        self.predict()
        kalman_gain = self.error_cov / (self.error_cov + self.measurement_noise)
        self.estimate += kalman_gain * (measurement - self.estimate)
        self.error_cov *= 1 - kalman_gain
        return self.estimate


def _load_filter(location_id: int, variable: str) -> KalmanFilter1D | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT estimate, error_cov FROM weather_kalman_state
            WHERE location_id = ? AND variable = ?
            """,
            (location_id, variable),
        ).fetchone()
    if not row:
        return None
    return KalmanFilter1D(float(row["estimate"]), float(row["error_cov"]))


def _save_filter(location_id: int, variable: str, kf: KalmanFilter1D) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO weather_kalman_state (
                location_id, variable, estimate, error_cov, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(location_id, variable) DO UPDATE SET
                estimate = excluded.estimate,
                error_cov = excluded.error_cov,
                updated_at = excluded.updated_at
            """,
            (location_id, variable, kf.estimate, kf.error_cov, _utcnow()),
        )


def update_from_observation(location_id: int, obs: dict) -> None:
    mapping = {
        "temp_f": obs.get("temp_f"),
        "humidity_pct": obs.get("humidity_pct"),
        "rain_chance_pct": None,
    }
    for var, val in mapping.items():
        if val is None:
            continue
        kf = _load_filter(location_id, var) or KalmanFilter1D(float(val))
        if _load_filter(location_id, var) is None:
            kf.estimate = float(val)
        else:
            kf.update(float(val))
        _save_filter(location_id, var, kf)


def apply_kalman(
    location_id: int,
    predictions: dict[str, float],
) -> dict[str, float]:
    """Blend model predictions with Kalman state estimates."""
    out = dict(predictions)
    blend = 0.35
    for var in KALMAN_VARS:
        if var not in out:
            continue
        kf = _load_filter(location_id, var)
        if kf is None:
            continue
        pred_val = float(out[var])
        out[var] = pred_val * (1 - blend) + kf.estimate * blend
    return out


def kalman_uncertainty(location_id: int) -> float | None:
    kf = _load_filter(location_id, "temp_f")
    if kf is None:
        return None
    return max(0.5, min(5.0, kf.error_cov ** 0.5))
