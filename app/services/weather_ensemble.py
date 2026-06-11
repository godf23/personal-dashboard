"""Trimmed-mean ensemble and source-spread uncertainty."""

from __future__ import annotations

import copy
import math


def trimmed_mean(values: list[float], trim: float = 0.1) -> float:
    """Drop top/bottom trim fraction, average the rest."""
    if not values:
        raise ValueError("trimmed_mean requires at least one value")
    if len(values) < 3:
        return sum(values) / len(values)
    sorted_v = sorted(values)
    k = max(1, int(len(sorted_v) * trim))
    if k * 2 >= len(sorted_v):
        return sum(sorted_v) / len(sorted_v)
    trimmed = sorted_v[k:-k]
    return sum(trimmed) / len(trimmed)


def uncertainty_iqr(values: list[float]) -> float:
    """Half the inter-quartile range as a calibrated spread estimate."""
    if len(values) < 2:
        return 0.5
    sorted_v = sorted(values)
    n = len(sorted_v)
    q1 = sorted_v[n // 4]
    q3 = sorted_v[(3 * n) // 4]
    return max((q3 - q1) / 2.0, 0.25)


def source_weight(source: dict, score: float = 1.0) -> float:
    base = float(source.get("confidence", 0.5)) * max(0.05, score)
    return base


def weighted_trimmed_mean(
    values: list[float],
    weights: list[float],
    trim: float = 0.1,
) -> float:
    if not values:
        raise ValueError("weighted_trimmed_mean requires values")
    if len(values) != len(weights):
        raise ValueError("values and weights length mismatch")
    if len(values) < 3:
        total_w = sum(weights) or 1.0
        return sum(v * w for v, w in zip(values, weights)) / total_w
    pairs = sorted(zip(values, weights), key=lambda p: p[0])
    vals = [p[0] for p in pairs]
    wts = [p[1] for p in pairs]
    k = max(1, int(len(vals) * trim))
    if k * 2 >= len(vals):
        total_w = sum(wts) or 1.0
        return sum(v * w for v, w in zip(vals, wts)) / total_w
    trimmed_vals = vals[k:-k]
    trimmed_wts = wts[k:-k]
    total_w = sum(trimmed_wts) or 1.0
    return sum(v * w for v, w in zip(trimmed_vals, trimmed_wts)) / total_w


def classical_weighted_mean(sources: list[dict], weights: dict[str, float] | None = None) -> float:
    total = 0.0
    wsum = 0.0
    for s in sources:
        w = source_weight(s, (weights or {}).get(s["source"], 1.0))
        total += s["temp_f"] * w
        wsum += w
    return total / wsum if wsum else sources[0]["temp_f"]


def aggregate_sources(
    sources: list[dict],
    source_scores: dict[str, float] | None = None,
    trim: float = 0.1,
) -> dict[str, float]:
    """Aggregate temp, humidity, rain from bias-corrected source dicts."""
    scores = source_scores or {}
    temps = []
    temp_weights = []
    humidities = []
    humidity_weights = []
    rains = []
    rain_weights = []

    for s in sources:
        w = source_weight(s, scores.get(s["source"], 1.0))
        temps.append(float(s["temp_f"]))
        temp_weights.append(w)
        humidities.append(float(s.get("humidity") or 60))
        humidity_weights.append(w)
        rains.append(float(s.get("rain_chance") or 0))
        rain_weights.append(w)

    return {
        "temp_f": weighted_trimmed_mean(temps, temp_weights, trim),
        "humidity": weighted_trimmed_mean(humidities, humidity_weights, trim),
        "rain_chance": weighted_trimmed_mean(rains, rain_weights, trim),
        "uncertainty_f": uncertainty_iqr(temps),
    }


def apply_score_downweight(sources: list[dict], scores: dict[str, float]) -> list[dict]:
    """Return copies with confidence scaled by verification scores."""
    out = []
    for s in sources:
        copy_s = copy.deepcopy(s)
        score = scores.get(s["source"], 1.0)
        copy_s["confidence"] = float(copy_s.get("confidence", 0.5)) * score
        out.append(copy_s)
    return out
