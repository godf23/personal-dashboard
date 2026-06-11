#!/usr/bin/env python3
"""
Personal Dashboard CLI

Usage:
  python dash.py /help
  python dash.py /version
  python dash.py /update
  python dash.py /restart
  python dash.py /debug
  python dash.py /logs
  python dash.py /weather-stats
  python dash.py run          # start the server
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.config import BASE_DIR, get_settings
from app.services.restart import restart_dashboard
from app.services.updater import apply_update_sync, check_for_update, get_local_short_commit
from app.version import __build__, __version__

COMMANDS = {
    "/help": "Show this help",
    "/version": "Show build version",
    "/update": "Pull latest code from GitHub",
    "/restart": "Restart the dashboard",
    "/debug": "Live debug console (playit-style logs)",
    "/logs": "Export logs to logs/<date-time>/ by category",
    "/weather-stats": "Show weather pipeline stage and observation counts",
    "run": "Start the dashboard server",
}


def _normalize_cmd(raw: str) -> str:
    cmd = raw.strip().lower()
    if cmd in ("help", "/help", "-h", "--help"):
        return "/help"
    if cmd in ("version", "/version", "-v", "--version"):
        return "/version"
    if cmd in ("update", "/update"):
        return "/update"
    if cmd in ("restart", "/restart"):
        return "/restart"
    if cmd in ("debug", "/debug"):
        return "/debug"
    if cmd in ("logs", "/logs", "export-logs", "/export-logs"):
        return "/logs"
    if cmd in ("weather-stats", "/weather-stats", "weather", "/weather"):
        return "/weather-stats"
    if cmd in ("run", "/run", "start", "/start"):
        return "run"
    return cmd


def cmd_help():
    print("Personal Dashboard CLI\n")
    for name, desc in COMMANDS.items():
        print(f"  {name:<12} {desc}")
    print("\nExamples:")
    print("  python dash.py /update")
    print("  python dash.py /restart")
    print("  python dash.py /debug")
    print("  python dash.py /logs")
    print("  python dash.py /weather-stats")
    print("  python dash.py run")


def cmd_version():
    commit = get_local_short_commit()
    suffix = f"  [{commit}]" if commit else ""
    print(f"Personal Dashboard  build {__build__}  (v{__version__}){suffix}")


def cmd_update():
    settings = get_settings()
    print(f"Checking {settings.github_repo}@{settings.github_branch}...")
    status = asyncio.run(
        check_for_update(settings.github_repo, settings.github_branch, force=True)
    )
    if not status.get("updates_supported"):
        print(status.get("error") or "Updates not supported", file=sys.stderr)
        sys.exit(1)
    if not status.get("update_available"):
        print("Already on the latest build.")
        return

    print("Downloading latest build...")
    result = apply_update_sync(settings.github_branch)
    if not result.get("ok"):
        print(result.get("error", "Update failed"), file=sys.stderr)
        sys.exit(1)

    sha = result.get("local_short_sha", "latest")
    print(f"Updated to {sha}.")
    if result.get("restarted"):
        print("Service restarted.")
    else:
        print("Run: python dash.py /restart")


def cmd_restart():
    print("Restarting dashboard...")
    result = restart_dashboard()
    if not result.get("ok"):
        print(result.get("error", "Restart failed"), file=sys.stderr)
        sys.exit(1)
    print(result.get("message", "Done."))


def cmd_debug():
    from app.services.debug_tui import run_debug_tui

    run_debug_tui()


def cmd_logs():
    from app.services.log_export import export_logs

    export_logs()


def cmd_weather_stats():
    from app.database import init_db
    from app.services.weather_bias import load_bias_map
    from app.services.weather_observations import all_pipeline_stats

    init_db()
    stats = all_pipeline_stats()
    if not stats:
        print("No weather locations configured.")
        return
    for s in stats:
        print(f"\n{s.get('label') or s['location_id']} (id={s['location_id']})")
        print(f"  Stage:           {s['pipeline_stage']}")
        print(f"  Obs days/count:  {s['observation_days']} / {s['observation_count']}")
        print(f"  Nearest station: {s.get('nearest_station') or '—'}")
        nxt = s.get("days_until_upgrade")
        print(f"  Next upgrade:    {nxt if nxt is not None else 'max stage'} day(s)")
        bias = load_bias_map(s["location_id"])
        if bias:
            print("  Per-source bias (temp_f):")
            for src, vars_ in sorted(bias.items()):
                if "temp_f" in vars_:
                    print(f"    {src}: {vars_['temp_f']:+.2f}°F")


def cmd_run():
    from start import run_server

    run_server()


def main():
    os.chdir(BASE_DIR)
    parser = argparse.ArgumentParser(
        description="Personal Dashboard CLI",
        add_help=False,
    )
    parser.add_argument("command", nargs="?", default="/help")
    args = parser.parse_args()

    cmd = _normalize_cmd(args.command)
    if cmd == "/help":
        cmd_help()
    elif cmd == "/version":
        cmd_version()
    elif cmd == "/update":
        cmd_update()
    elif cmd == "/restart":
        cmd_restart()
    elif cmd == "/debug":
        cmd_debug()
    elif cmd == "/logs":
        cmd_logs()
    elif cmd == "/weather-stats":
        cmd_weather_stats()
    elif cmd == "run":
        cmd_run()
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        print("Run: python dash.py /help", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
