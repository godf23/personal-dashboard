#!/usr/bin/env python3
"""
Personal Dashboard CLI

Usage:
  python dash.py /help
  python dash.py /version
  python dash.py /update
  python dash.py /restart
  python dash.py /debug
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
    if cmd in ("debug", "/debug", "logs", "/logs"):
        return "/debug"
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
    elif cmd == "run":
        cmd_run()
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        print("Run: python dash.py /help", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
