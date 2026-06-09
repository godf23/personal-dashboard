"""Download Icons8 PNG assets for the dashboard."""

import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"

WEATHER = {
    "clear": "648",
    "partly_cloudy": "2767",
    "cloudy": "4xttFVmp97nX",
    "rain": "18567",
    "showers": "2767",
    "drizzle": "18567",
    "thunderstorm": "41144",
    "snow": "664",
    "fog": "674",
    "unknown": "648",
}

UI = {
    "menu": "120374",
    "plus": "1501",
    "cpu": "16630",
    "storage": "178",
    "news": "532",
    "humidity": "1690",
    "wind": "31842",
    "close": "46",
    "external-link": "742",
    "rain": "2767",
}


def download(icon_id: str, dest: Path) -> None:
    url = f"https://img.icons8.com/?id={icon_id}&format=png&size=64"
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"Saved {dest.name}")


def main():
    for name, iid in WEATHER.items():
        download(iid, BASE / "weather" / f"{name}.png")
    for name, iid in UI.items():
        download(iid, BASE / "ui" / f"{name}.png")


if __name__ == "__main__":
    main()
