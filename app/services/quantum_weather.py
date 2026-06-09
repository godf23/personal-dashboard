"""Quantum Weather Engine - standalone port from weather preditor.py."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import requests

from app.services.weather_icons import summary_to_icon_key

UA = "QuantumWeatherEngine/2.0 (dashboard)"


def wmo_str(code: int | None) -> str:
    return {
        0: "Clear",
        1: "Mainly Clear",
        2: "Partly Cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Icy Fog",
        51: "Light Drizzle",
        53: "Drizzle",
        61: "Light Rain",
        63: "Rain",
        65: "Heavy Rain",
        71: "Light Snow",
        73: "Snow",
        80: "Showers",
        95: "Thunderstorm",
    }.get(code, f"Code {code}")


def fetch_nws(lat: float, lon: float) -> dict:
    try:
        pts = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers={"User-Agent": UA},
            timeout=10,
        ).json()
        fc = requests.get(pts["properties"]["forecast"], timeout=10).json()
        p = fc["properties"]["periods"][0]
        return {
            "source": "NWS",
            "temp_f": float(p["temperature"]),
            "feels_like": None,
            "summary": p["shortForecast"],
            "humidity": p.get("relativeHumidity", {}).get("value"),
            "wind_mph": None,
            "rain_chance": p.get("probabilityOfPrecipitation", {}).get("value", 0) or 0,
            "confidence": 0.92,
        }
    except Exception as e:
        return {"source": "NWS", "error": True, "confidence": 0, "err_msg": str(e)}


def fetch_open_meteo(lat: float, lon: float) -> dict:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            f"precipitation_probability,weather_code,wind_speed_10m,"
            f"surface_pressure,cloud_cover,dew_point_2m,uv_index"
            f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        )
        d = requests.get(url, timeout=10).json()["current"]
        return {
            "source": "Open-Meteo",
            "temp_f": float(d["temperature_2m"]),
            "feels_like": float(d.get("apparent_temperature", d["temperature_2m"])),
            "summary": wmo_str(d.get("weather_code")),
            "humidity": d.get("relative_humidity_2m"),
            "wind_mph": d.get("wind_speed_10m"),
            "rain_chance": d.get("precipitation_probability", 0) or 0,
            "pressure_hpa": d.get("surface_pressure"),
            "cloud_cover": d.get("cloud_cover"),
            "dew_point_f": d.get("dew_point_2m"),
            "uv_index": d.get("uv_index"),
            "weather_code": d.get("weather_code"),
            "confidence": 0.90,
        }
    except Exception as e:
        return {"source": "Open-Meteo", "error": True, "confidence": 0, "err_msg": str(e)}


def fetch_met_norway(lat: float, lon: float) -> dict:
    try:
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10).json()
        d = r["properties"]["timeseries"][0]["data"]["instant"]["details"]
        next1h = r["properties"]["timeseries"][0]["data"].get("next_1_hours", {})
        summary = next1h.get("summary", {}).get("symbol_code", "unknown")
        precip = next1h.get("details", {}).get("precipitation_amount", 0) or 0
        rain_chance = min(int(precip * 25), 100)
        temp_c = d.get("air_temperature", 0)
        temp_f = temp_c * 9 / 5 + 32
        wind_ms = d.get("wind_speed", 0)
        wind_mph = wind_ms * 2.237
        return {
            "source": "MET Norway",
            "temp_f": float(temp_f),
            "feels_like": None,
            "summary": summary.replace("_", " ").title(),
            "humidity": d.get("relative_humidity"),
            "wind_mph": round(wind_mph, 1),
            "rain_chance": rain_chance,
            "pressure_hpa": d.get("air_pressure_at_sea_level"),
            "cloud_cover": d.get("cloud_area_fraction"),
            "confidence": 0.88,
        }
    except Exception as e:
        return {"source": "MET Norway", "error": True, "confidence": 0, "err_msg": str(e)}


def fetch_7timer(lat: float, lon: float) -> dict:
    try:
        url = f"http://www.7timer.info/bin/api.pl?lon={lon}&lat={lat}&product=civil&output=json"
        r = requests.get(url, timeout=12).json()
        d = r["dataseries"][0]
        temp_c = d.get("temp2m", 0)
        temp_f = temp_c * 9 / 5 + 32
        rh_map = {
            "0-10": 5, "10-20": 15, "20-30": 25, "30-40": 35,
            "40-50": 45, "50-60": 55, "60-70": 65, "70-80": 75,
            "80-90": 85, "90-100": 95,
        }
        humidity = rh_map.get(str(d.get("rh2m", "50-60")), 60)
        prec_map = {-1: 0, 0: 0, 1: 5, 2: 20, 3: 40, 4: 60, 5: 80, 6: 90, 7: 100, 8: 100}
        rain_chance = prec_map.get(d.get("prec_type", 0), 0)
        wind_map = {1: 1, 2: 5, 3: 11, 4: 17, 5: 23, 6: 30, 7: 38, 8: 47}
        wind_mph = wind_map.get(d.get("wind10m", {}).get("speed", 1), 5)
        weather_map = {
            "clearday": "Clear", "clearnight": "Clear",
            "pcloudyday": "Partly Cloudy", "pcloudynight": "Partly Cloudy",
            "mcloudyday": "Mostly Cloudy", "cloudyday": "Cloudy",
            "humidday": "Humid", "lightrainday": "Light Rain",
            "oshowerday": "Showers", "rainday": "Rain", "tsrainday": "Thunderstorm",
        }
        summary = weather_map.get(d.get("weather", ""), d.get("weather", "Unknown"))
        return {
            "source": "7Timer",
            "temp_f": float(temp_f),
            "feels_like": None,
            "summary": summary,
            "humidity": humidity,
            "wind_mph": wind_mph,
            "rain_chance": rain_chance,
            "confidence": 0.82,
        }
    except Exception as e:
        return {"source": "7Timer", "error": True, "confidence": 0, "err_msg": str(e)}


def fetch_owm(lat: float, lon: float, api_key: str) -> dict:
    if not api_key:
        return {"source": "OpenWeatherMap", "skipped": True, "confidence": 0}
    try:
        d = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={api_key}&units=imperial",
            timeout=10,
        ).json()
        m = d["main"]
        return {
            "source": "OpenWeatherMap",
            "temp_f": float(m["temp"]),
            "feels_like": float(m.get("feels_like", m["temp"])),
            "summary": d["weather"][0]["description"].title(),
            "humidity": m.get("humidity"),
            "wind_mph": d["wind"].get("speed"),
            "rain_chance": 0,
            "pressure_hpa": m.get("pressure"),
            "confidence": 0.87,
        }
    except Exception as e:
        return {"source": "OpenWeatherMap", "error": True, "confidence": 0, "err_msg": str(e)}


def fetch_weatherapi(lat: float, lon: float, api_key: str) -> dict:
    if not api_key:
        return {"source": "WeatherAPI.com", "skipped": True, "confidence": 0}
    try:
        d = requests.get(
            f"https://api.weatherapi.com/v1/current.json?key={api_key}&q={lat},{lon}",
            timeout=10,
        ).json()["current"]
        return {
            "source": "WeatherAPI.com",
            "temp_f": float(d["temp_f"]),
            "feels_like": float(d.get("feelslike_f", d["temp_f"])),
            "summary": d["condition"]["text"],
            "humidity": d.get("humidity"),
            "wind_mph": d.get("wind_mph"),
            "rain_chance": d.get("chance_of_rain", 0) or 0,
            "pressure_hpa": d.get("pressure_mb"),
            "cloud_cover": d.get("cloud"),
            "uv_index": d.get("uv"),
            "confidence": 0.87,
        }
    except Exception as e:
        return {"source": "WeatherAPI.com", "error": True, "confidence": 0, "err_msg": str(e)}


def divergence_adjusted_weights(sources: list[dict]) -> list[float]:
    temps = [s["temp_f"] for s in sources]
    mean = sum(temps) / len(temps)
    variance = sum((t - mean) ** 2 for t in temps) / len(temps)
    std = math.sqrt(variance) if variance > 0 else 0.01
    adjusted = []
    for s in sources:
        z = abs(s["temp_f"] - mean) / std
        penalty = 1.0 / (1.0 + math.exp(z - 1.5))
        adjusted.append(s["confidence"] * penalty)
    total = sum(adjusted)
    return [w / total for w in adjusted]


def adaptive_shots(sources: list[dict]) -> int:
    temps = [s["temp_f"] for s in sources]
    spread = max(temps) - min(temps)
    shots = int(65536 + (spread / 5.0) * (524288 - 65536))
    shots = max(65536, min(524288, shots))
    return 2 ** math.ceil(math.log2(shots))


def find_dominant_cluster(sources: list[dict]) -> list[int]:
    temps = [s["temp_f"] for s in sources]
    mean = sum(temps) / len(temps)
    variance = sum((t - mean) ** 2 for t in temps) / len(temps)
    std = math.sqrt(variance) if variance > 0 else 0.5
    return [i for i, s in enumerate(sources) if abs(s["temp_f"] - mean) <= std]


def grover_reflection(qc, qr, target_indices: list[int]) -> None:
    for i in target_indices:
        qc.z(qr[i])
    for i in range(len(qr)):
        qc.h(qr[i])
        qc.x(qr[i])
    if len(qr) > 1:
        qc.h(qr[-1])
        qc.mcx(list(range(len(qr) - 1)), qr[-1])
        qc.h(qr[-1])
    for i in range(len(qr)):
        qc.x(qr[i])
        qc.h(qr[i])


def quantum_ensemble(sources: list[dict]) -> tuple[dict, float, int, list[float]]:
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
    from qiskit_aer import AerSimulator

    n = len(sources)
    norm_w = divergence_adjusted_weights(sources)
    shots = adaptive_shots(sources)
    runs = 3
    dominant = find_dominant_cluster(sources)
    variables = {
        "temp_f": [s["temp_f"] for s in sources],
        "humidity": [float(s.get("humidity") or 60) for s in sources],
        "rain_chance": [float(s.get("rain_chance") or 0) for s in sources],
    }
    results: dict[str, float] = {}
    for var_name, values in variables.items():
        final_val = 0.0
        for _ in range(runs):
            qr = QuantumRegister(n, "q")
            cr = ClassicalRegister(n, "c")
            qc = QuantumCircuit(qr, cr)
            for i, w in enumerate(norm_w):
                theta = 2 * math.asin(math.sqrt(min(w, 1.0)))
                qc.ry(theta, qr[i])
                qc.rz(math.pi * w, qr[i])
            for i in range(n):
                for j in range(i + 1, n):
                    qc.cx(qr[i], qr[j])
            if 0 < len(dominant) < n:
                grover_reflection(qc, qr, dominant)
            qc.measure(qr, cr)
            sim = AerSimulator()
            tqc = transpile(qc, sim)
            result = sim.run(tqc, shots=shots).result()
            counts = result.get_counts()
            q_val = 0.0
            total_p = 0.0
            for bitstring, count in counts.items():
                prob = count / shots
                bits = [int(b) for b in reversed(bitstring)]
                selected = [values[i] for i, b in enumerate(bits) if b == 1]
                if selected:
                    avg_v = sum(selected) / len(selected)
                    q_val += prob * avg_v
                    total_p += prob
            q_val = (q_val / total_p) if total_p > 0 else sum(
                v * w for v, w in zip(values, norm_w)
            )
            final_val += q_val
        results[var_name] = final_val / runs
    temps = variables["temp_f"]
    std_dev = math.sqrt(
        sum(w * (t - results["temp_f"]) ** 2 for t, w in zip(temps, norm_w))
    )
    return results, std_dev, shots, norm_w


def get_weather(
    lat: float,
    lon: float,
    owm_key: str = "",
    wapi_key: str = "",
) -> dict | None:
    sources_raw = [
        fetch_nws(lat, lon),
        fetch_open_meteo(lat, lon),
        fetch_met_norway(lat, lon),
        fetch_7timer(lat, lon),
        fetch_owm(lat, lon, owm_key),
        fetch_weatherapi(lat, lon, wapi_key),
    ]
    valid = [
        s for s in sources_raw
        if "temp_f" in s and not s.get("skipped") and not s.get("error")
    ]
    if not valid:
        return None

    total_conf = sum(s["confidence"] for s in valid)
    classical_temp = sum(s["temp_f"] * s["confidence"] for s in valid) / total_conf

    q_results, q_std, _, _ = quantum_ensemble(valid)
    best_src = max(valid, key=lambda x: x["confidence"])
    summary = best_src.get("summary", "N/A")
    om = next((s for s in valid if s["source"] == "Open-Meteo"), None)

    wind = best_src.get("wind_mph")
    if wind is None:
        for s in valid:
            if s.get("wind_mph") is not None:
                wind = s["wind_mph"]
                break

    return {
        "temperature_f": round(q_results["temp_f"], 1),
        "uncertainty_f": round(q_std, 2),
        "classical_temp_f": round(classical_temp, 1),
        "humidity_pct": round(q_results["humidity"]),
        "rain_chance_pct": round(q_results["rain_chance"]),
        "summary": summary,
        "icon_key": summary_to_icon_key(summary),
        "wind_mph": wind,
        "pressure_hpa": om.get("pressure_hpa") if om else None,
        "cloud_cover_pct": om.get("cloud_cover") if om else None,
        "dew_point_f": om.get("dew_point_f") if om else None,
        "uv_index": om.get("uv_index") if om else None,
        "active_sources": len(valid),
        "total_sources": 6,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
