"""XGBoost quantile regression training and inference."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import BASE_DIR
from app.database import get_db
from app.services.weather_features import SOURCE_ORDER, feature_names, feature_vector

MODELS_DIR = BASE_DIR / "data" / "models"
QUANTILES = (0.1, 0.5, 0.9)


def _model_path(location_id: int) -> Path:
    return MODELS_DIR / f"weather_{location_id}.json"


def _model_meta_path(location_id: int) -> Path:
    return MODELS_DIR / f"weather_{location_id}_meta.json"


def _training_pairs(location_id: int, window_days: int = 60) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT o.temp_f AS observed, o.observed_at,
                   GROUP_CONCAT(p.source_name || ':' || p.temp_f) AS source_temps
            FROM weather_observations o
            JOIN weather_predictions_log p
              ON p.location_id = o.location_id
             AND substr(p.logged_at, 1, 13) = substr(o.observed_at, 1, 13)
            WHERE o.location_id = ?
              AND o.observed_at >= ?
              AND o.temp_f IS NOT NULL
              AND p.temp_f IS NOT NULL
            GROUP BY o.id
            ORDER BY o.observed_at
            """,
            (location_id, start),
        ).fetchall()

    samples = []
    for row in rows:
        temps: dict[str, float] = {}
        if row["source_temps"]:
            for part in str(row["source_temps"]).split(","):
                if ":" in part:
                    name, val = part.split(":", 1)
                    temps[name] = float(val)
        sources = [{"source": n, "temp_f": t} for n, t in temps.items()]
        if not sources:
            continue
        from app.services.weather_bias import apply_bias_to_sources

        with get_db() as conn:
            loc = conn.execute(
                "SELECT lat, lon FROM weather_locations WHERE id = ?",
                (location_id,),
            ).fetchone()
        if not loc:
            continue
        corrected, _, _ = apply_bias_to_sources(sources, location_id)
        from app.services.weather_features import extract_features

        feats = extract_features(corrected, location_id, loc["lat"], loc["lon"])
        samples.append({"features": feats, "target": float(row["observed"])})
    return samples


def train_location_model(location_id: int, window_days: int = 60) -> bool:
    try:
        import xgboost as xgb
        import numpy as np
    except ImportError:
        return False

    samples = _training_pairs(location_id, window_days)
    if len(samples) < 48:
        return False

    names = feature_names()
    x = np.array([[s["features"].get(n, 0.0) for n in names] for s in samples])
    y = np.array([s["target"] for s in samples])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    models = {}
    for q in QUANTILES:
        model = xgb.XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=q,
            n_estimators=80,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
        )
        model.fit(x, y)
        models[str(q)] = model

    for q, model in models.items():
        path = MODELS_DIR / f"weather_{location_id}_q{q.replace('.', '')}.json"
        model.save_model(str(path))

    meta = {
        "location_id": location_id,
        "feature_names": names,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "samples": len(samples),
        "quantiles": list(QUANTILES),
    }
    _model_meta_path(location_id).write_text(json.dumps(meta), encoding="utf-8")
    return True


def model_available(location_id: int) -> bool:
    return _model_meta_path(location_id).exists()


def predict_temp_quantiles(
    location_id: int,
    features: dict[str, float],
) -> dict[str, float] | None:
    try:
        import xgboost as xgb
        import numpy as np
    except ImportError:
        return None

    meta_path = _model_meta_path(location_id)
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    names = meta["feature_names"]
    x = np.array([[features.get(n, 0.0) for n in names]])

    out: dict[str, float] = {}
    for q in meta.get("quantiles", QUANTILES):
        path = MODELS_DIR / f"weather_{location_id}_q{str(q).replace('.', '')}.json"
        if not path.exists():
            return None
        model = xgb.XGBRegressor()
        model.load_model(str(path))
        out[str(q)] = float(model.predict(x)[0])
    return out


def retrain_all_eligible(min_days: int = 60, window_days: int = 60) -> dict[int, bool]:
    from app.services.weather_observations import observation_days

    results = {}
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM weather_locations").fetchall()
    for row in rows:
        if observation_days(row["id"]) >= min_days:
            results[row["id"]] = train_location_model(row["id"], window_days)
    return results
