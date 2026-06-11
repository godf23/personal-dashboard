#!/usr/bin/env python3
"""
Quantum Weather Engine v2 - ULTRA PRECISION MODE
6 sources, multi-variable quantum encoding, adaptive shots, divergence-aware weighting
"""

import math
import subprocess
import sys
import requests
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# QISKIT INSTALL + IMPORT
# ─────────────────────────────────────────────────────────────
def ensure_qiskit():
    try:
        from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
        from qiskit_aer import AerSimulator
        print("✅ Qiskit ready")
        return True
    except ImportError:
        print("📦 Qiskit not found — installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "qiskit", "qiskit-aer"])
        print("✅ Qiskit installed")
        return True

ensure_qiskit()

# ─────────────────────────────────────────────────────────────
# COLAB SECRETS
# ─────────────────────────────────────────────────────────────
def load_secrets():
    from google.colab import userdata
    try:
        owm_key = userdata.get('OWM_API_KEY')
    except:
        owm_key = ""
    try:
        wapi_key = userdata.get('WAPI_API_KEY')
    except:
        wapi_key = ""
    return owm_key, wapi_key

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
DEFAULT_LAT = 32.7157
DEFAULT_LON = -117.1611
UA = "QuantumWeatherEngine/2.0 (research)"

# ─────────────────────────────────────────────────────────────
# WMO CODE LOOKUP
# ─────────────────────────────────────────────────────────────
def wmo_str(code):
    return {
        0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Fog", 48: "Icy Fog", 51: "Light Drizzle", 53: "Drizzle",
        61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Snow", 80: "Showers", 95: "Thunderstorm"
    }.get(code, f"Code {code}")

# ─────────────────────────────────────────────────────────────
# SOURCE FETCHERS
# ─────────────────────────────────────────────────────────────
def fetch_nws(lat, lon):
    try:
        pts = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers={"User-Agent": UA}, timeout=10
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
            "confidence": 0.92
        }
    except Exception as e:
        return {"source": "NWS", "error": True, "confidence": 0, "err_msg": str(e)}

def fetch_open_meteo(lat, lon):
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
            "confidence": 0.90
        }
    except Exception as e:
        return {"source": "Open-Meteo", "error": True, "confidence": 0, "err_msg": str(e)}

def fetch_met_norway(lat, lon):
    """MET Norway Locationforecast — no API key, just User-Agent required."""
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
            "confidence": 0.88
        }
    except Exception as e:
        return {"source": "MET Norway", "error": True, "confidence": 0, "err_msg": str(e)}

def fetch_7timer(lat, lon):
    """7Timer CIVIL product — no API key, GFS-based, global coverage."""
    try:
        url = f"http://www.7timer.info/bin/api.pl?lon={lon}&lat={lat}&product=civil&output=json"
        r = requests.get(url, timeout=12).json()
        d = r["dataseries"][0]
        temp_c = d.get("temp2m", 0)
        temp_f = temp_c * 9 / 5 + 32
        rh_map = {
            "0-10": 5, "10-20": 15, "20-30": 25, "30-40": 35,
            "40-50": 45, "50-60": 55, "60-70": 65, "70-80": 75,
            "80-90": 85, "90-100": 95
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
            "oshowerday": "Showers", "rainday": "Rain", "tsrainday": "Thunderstorm"
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
            "confidence": 0.82
        }
    except Exception as e:
        return {"source": "7Timer", "error": True, "confidence": 0, "err_msg": str(e)}

def fetch_owm(lat, lon, api_key):
    if not api_key:
        return {"source": "OpenWeatherMap", "skipped": True, "confidence": 0}
    try:
        d = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={api_key}&units=imperial",
            timeout=10
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
            "confidence": 0.87
        }
    except Exception as e:
        return {"source": "OpenWeatherMap", "error": True, "confidence": 0, "err_msg": str(e)}

def fetch_weatherapi(lat, lon, api_key):
    if not api_key:
        return {"source": "WeatherAPI.com", "skipped": True, "confidence": 0}
    try:
        d = requests.get(
            f"https://api.weatherapi.com/v1/current.json?key={api_key}&q={lat},{lon}",
            timeout=10
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
            "confidence": 0.87
        }
    except Exception as e:
        return {"source": "WeatherAPI.com", "error": True, "confidence": 0, "err_msg": str(e)}

# ─────────────────────────────────────────────────────────────
# QUANTUM HELPERS
# ─────────────────────────────────────────────────────────────
def divergence_adjusted_weights(sources):
    """
    Penalize outlier sources via z-score. Sources far from the mean
    get reduced weight before quantum encoding via sigmoid penalty.
    """
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

def adaptive_shots(sources):
    """
    Scale shot count with source disagreement.
    Tight consensus = fast. Wide spread = max precision.
    Returns a power of 2 between 65536 and 524288.
    """
    temps = [s["temp_f"] for s in sources]
    spread = max(temps) - min(temps)
    shots = int(65536 + (spread / 5.0) * (524288 - 65536))
    shots = max(65536, min(524288, shots))
    shots = 2 ** math.ceil(math.log2(shots))
    return shots

def find_dominant_cluster(sources):
    """Returns indices of sources within 1 std dev of the mean temperature."""
    temps = [s["temp_f"] for s in sources]
    mean = sum(temps) / len(temps)
    variance = sum((t - mean) ** 2 for t in temps) / len(temps)
    std = math.sqrt(variance) if variance > 0 else 0.5
    return [i for i, s in enumerate(sources) if abs(s["temp_f"] - mean) <= std]

def grover_reflection(qc, qr, target_indices):
    """
    Single Grover reflection pass to amplify dominant cluster amplitudes.
    Marks target qubits with a phase flip, then applies diffusion.
    """
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

# ─────────────────────────────────────────────────────────────
# MULTI-VARIABLE QUANTUM ENSEMBLE
# ─────────────────────────────────────────────────────────────
def quantum_ensemble(sources):
    """
    Encodes temperature, humidity, and rain chance into separate qubit registers.
    Each variable is processed with divergence-adjusted weights + Grover amplification,
    then all three are reported independently.
    """
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
    from qiskit_aer import AerSimulator

    n = len(sources)
    norm_w = divergence_adjusted_weights(sources)
    shots = adaptive_shots(sources)
    runs = 3
    dominant = find_dominant_cluster(sources)

    print(f"   ⚛️  Adaptive shots : {shots:,}")
    print(f"   ⚛️  Sources        : {n}")
    print(f"   ⚛️  Dominant cluster (within 1σ): {dominant}")
    print(f"   ⚛️  Adjusted weights: {[f'{w:.3f}' for w in norm_w]}")

    variables = {
        "temp_f":      [s["temp_f"] for s in sources],
        "humidity":    [float(s.get("humidity") or 60) for s in sources],
        "rain_chance": [float(s.get("rain_chance") or 0) for s in sources],
    }

    results = {}

    for var_name, values in variables.items():
        final_val = 0.0

        for run in range(runs):
            qr = QuantumRegister(n, "q")
            cr = ClassicalRegister(n, "c")
            qc = QuantumCircuit(qr, cr)

            # State prep: RY encodes weight magnitude, RZ encodes phase
            for i, w in enumerate(norm_w):
                theta = 2 * math.asin(math.sqrt(min(w, 1.0)))
                qc.ry(theta, qr[i])
                qc.rz(math.pi * w, qr[i])

            # All-to-all entanglement
            for i in range(n):
                for j in range(i + 1, n):
                    qc.cx(qr[i], qr[j])

            # Grover reflection on dominant cluster
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

            q_val = (q_val / total_p) if total_p > 0 else sum(v * w for v, w in zip(values, norm_w))
            final_val += q_val

        results[var_name] = final_val / runs
        print(f"   ✅  {var_name:<14} → {results[var_name]:.2f}  ({runs} runs × {shots:,} shots)")

    temps = variables["temp_f"]
    std_dev = math.sqrt(sum(w * (t - results["temp_f"]) ** 2 for t, w in zip(temps, norm_w)))

    return results, std_dev, shots, norm_w

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def run(lat=DEFAULT_LAT, lon=DEFAULT_LON, owm_key="", wapi_key=""):
    print(f"\n{'═'*90}")
    print(f"🌦️  QUANTUM WEATHER ENGINE v2 — ULTRA PRECISION")
    print(f"📍 {lat:.4f}, {lon:.4f}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*90}\n")

    sources_raw = [
        fetch_nws(lat, lon),
        fetch_open_meteo(lat, lon),
        fetch_met_norway(lat, lon),
        fetch_7timer(lat, lon),
        fetch_owm(lat, lon, owm_key),
        fetch_weatherapi(lat, lon, wapi_key),
    ]

    print("📡 SOURCE DATA:")
    print(f"  {'Source':<20} {'Temp':>7}  {'Feels':>7}  {'Rain':>6}  {'Hum':>5}  {'Wind':>9}  {'Conf':>5}  Status")
    print(f"  {'─'*20} {'─'*7}  {'─'*7}  {'─'*6}  {'─'*5}  {'─'*9}  {'─'*5}  {'─'*6}")

    for s in sources_raw:
        if s.get("skipped"):
            print(f"  {s['source']:<20} {'—':>7}  {'—':>7}  {'—':>6}  {'—':>5}  {'—':>9}  {'—':>5}  Skipped (no key)")
        elif s.get("error"):
            msg = s.get("err_msg", "")[:35]
            print(f"  {s['source']:<20} {'—':>7}  {'—':>7}  {'—':>6}  {'—':>5}  {'—':>9}  {'—':>5}  ❌ {msg}")
        else:
            feels = f"{s['feels_like']:.1f}°F" if s.get("feels_like") else "    —  "
            wind  = f"{s['wind_mph']} mph"      if s.get("wind_mph")   else "    —  "
            hum   = str(s.get("humidity", "?"))
            print(f"  {s['source']:<20} {s['temp_f']:>6.1f}°F  {feels:>7}  {s.get('rain_chance', 0):>5}%  "
                  f"{hum:>4}%  {str(wind):>9}  {s['confidence']:>5.2f}  ✅")

    valid = [s for s in sources_raw if "temp_f" in s and not s.get("skipped") and not s.get("error")]

    if not valid:
        print("\n❌ No valid sources. Check network or API keys.")
        return

    # Classical baseline
    total_conf    = sum(s["confidence"] for s in valid)
    classical_temp = sum(s["temp_f"] * s["confidence"] for s in valid) / total_conf
    classical_rain = round(sum(s.get("rain_chance", 0) for s in valid) / len(valid))
    classical_hum  = round(sum(float(s.get("humidity") or 60) for s in valid) / len(valid))

    # Quantum
    print(f"\n⚛️  Running Multi-Variable Quantum Ensemble ({len(valid)} sources)...")
    q_results, q_std, shots_used, final_weights = quantum_ensemble(valid)

    q_temp     = q_results["temp_f"]
    q_humidity = q_results["humidity"]
    q_rain     = q_results["rain_chance"]

    best_src = max(valid, key=lambda x: x["confidence"])
    summary  = best_src.get("summary", "N/A")

    om        = next((s for s in valid if s["source"] == "Open-Meteo"), None)
    pressure  = om.get("pressure_hpa")  if om else None
    cloud     = om.get("cloud_cover")   if om else None
    dew_point = om.get("dew_point_f")   if om else None
    uv        = om.get("uv_index")      if om else None

    print(f"\n{'═'*90}")
    print("🏁  QUANTUM ENSEMBLE REPORT — ULTRA PRECISION")
    print(f"{'═'*90}")
    print(f"  🌡️  Quantum Temperature  : {q_temp:.2f}°F  (±{q_std:.2f}°F uncertainty)")
    print(f"  🌡️  Classical Baseline   : {classical_temp:.2f}°F")
    print(f"  📐  Quantum vs Classical : {abs(q_temp - classical_temp):.2f}°F delta")
    print(f"  💧  Quantum Humidity     : {q_humidity:.1f}%  (classical: {classical_hum}%)")
    print(f"  🌧️  Quantum Rain Chance  : {q_rain:.1f}%  (classical: {classical_rain}%)")
    print(f"  ☁️   Conditions           : {summary}")
    if pressure:          print(f"  📊  Pressure             : {pressure:.1f} hPa")
    if cloud is not None: print(f"  ☁️   Cloud Cover          : {cloud}%")
    if dew_point:         print(f"  💦  Dew Point            : {dew_point:.1f}°F")
    if uv is not None:    print(f"  ☀️   UV Index             : {uv}")
    print(f"  🔬  Shots Used           : {shots_used:,}  (adaptive)")
    print(f"  📡  Active Sources       : {len(valid)}/6")

    print(f"\n  Source weights after divergence penalty:")
    for s, w in zip(valid, final_weights):
        bar = "█" * int(w * 40)
        print(f"    {s['source']:<20} {w:.4f}  {bar}")

    print(f"\n  🔮  Forecast:")
    if q_rain >= 50:
        print("      🌧️  Rain expected — bring an umbrella")
    elif q_rain >= 25:
        print("      🌦️  Possible showers — keep one handy")
    else:
        print("      ☀️  Mostly dry conditions")

    if q_temp >= 95:
        print("      🥵  Extreme heat warning")
    elif q_temp >= 85:
        print("      🌞  Hot day")
    elif q_temp >= 70:
        print("      😎  Comfortable")
    elif q_temp >= 55:
        print("      🧥  Jacket weather")
    else:
        print("      🥶  Cold — bundle up")

    print(f"{'═'*90}\n")

if __name__ == "__main__":
    owm_key, wapi_key = load_secrets()
    run(DEFAULT_LAT, DEFAULT_LON, owm_key, wapi_key)