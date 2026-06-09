# Personal Dashboard

A self-hosted personal dashboard with quantum weather, news feeds, and a sortable links grid.

## Features

- **Weather** — Multi-location quantum ensemble forecast with animated conditions and 7-day outlook
- **News** — The News API feeds with hover previews
- **Links** — CRUD bookmarks with favicons, click tracking, and sort modes
- **Settings** — Hamburger menu for locations and preferences (secrets stay in `.env`)

## Quick install (Linux)

One-liner (Debian/Ubuntu, Alpine, or RHEL/Fedora as root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/godf23/personal-dashboard/main/install/dashboard.sh)"
```

The installer will:

1. Install system dependencies (git, Python 3, venv)
2. Clone to `/opt/personal-dashboard` (configurable)
3. Create a Python virtualenv and install requirements
4. Copy `.env.example` → `.env`
5. Register a systemd service and start on port 8080 (configurable)

After install, edit `/opt/personal-dashboard/.env` with your API keys.

## Manual install

```bash
git clone https://github.com/godf23/personal-dashboard.git
cd personal-dashboard
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add your keys
python start.py
```

Open `http://127.0.0.1:8080` (or `:443` / `:80` if available and you have SSL certs).

## Environment variables

| Variable | Description |
|----------|-------------|
| `OWM_API_KEY` | OpenWeatherMap API key |
| `WAPI_API_KEY` | WeatherAPI.com key |
| `NEWS_API_TOKEN` | [The News API](https://www.thenewsapi.com/) token |
| `SSL_CERT` / `SSL_KEY` | Optional paths to TLS cert/key for HTTPS |

## Service management

```bash
systemctl status personal-dashboard
systemctl restart personal-dashboard
journalctl -u personal-dashboard -f
```

## License

MIT
