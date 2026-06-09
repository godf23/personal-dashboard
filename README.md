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
| `GITHUB_REPO` | GitHub repo for auto-updates (default: `godf23/personal-dashboard`) |
| `GITHUB_BRANCH` | Branch to track (default: `main`) |

## Auto-updates

When the dashboard runs from a git clone, it checks GitHub every 5 minutes. If you've pushed newer code, a prompt appears in the **bottom-left** with **Update now** / **Later**.

- **Linux (systemd install):** pulls latest code, refreshes dependencies, and restarts the service
- **Local dev:** pulls latest code; restart `start.py` when prompted

## Push to GitHub

```powershell
.\push.ps1 "describe your changes"
```

Or:

```bash
python scripts/push.py "describe your changes"
```

## CLI commands

**In the dashboard** (bottom-right command bar, or press `` ` `` to focus):

| Command | Action |
|---------|--------|
| `/help` | List commands |
| `/version` | Show build version |
| `/update` | Pull latest code from GitHub |
| `/restart` | Restart the dashboard |

**Terminal** (`start.py`):

```bash
python start.py              # run server (default)
python start.py version      # show build 0.1
python start.py update       # pull latest from GitHub
python start.py restart      # restart systemd service (Linux install)
```

Version metadata lives in `app/version.py` — bump `__build__` when you ship.

## Service management

```bash
systemctl status personal-dashboard
systemctl restart personal-dashboard
journalctl -u personal-dashboard -f
```

## License

MIT
