#!/usr/bin/env python3
"""Start the personal dashboard for local use or playit.gg tunneling."""

import argparse
import os
import socket
import sys

import uvicorn

from app.config import BASE_DIR, get_settings
from app.version import __build__, __version__

DEFAULT_PORTS = (443, 80, 8080)


def can_bind(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_port(host: str) -> int:
    if os.getenv("PORT"):
        return int(os.environ["PORT"])
    for port in DEFAULT_PORTS:
        if can_bind(host, port):
            return port
    raise RuntimeError(
        f"Ports {', '.join(map(str, DEFAULT_PORTS))} are all in use. "
        "Stop the other service or set PORT to a free port for playit.gg."
    )


def run_server():
    settings = get_settings()
    cert = settings.ssl_cert_path
    key = settings.ssl_key_path
    use_ssl = cert.exists() and key.exists()
    host = os.getenv("HOST", "0.0.0.0")

    try:
        port = pick_port(host)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    kwargs = {
        "app": "app.main:app",
        "host": host,
        "port": port,
        "reload": False,
    }

    if use_ssl:
        kwargs["ssl_certfile"] = str(cert)
        kwargs["ssl_keyfile"] = str(key)
        scheme = "https"
    else:
        scheme = "http"

    print(f"Personal Dashboard build {__build__} (v{__version__})")
    print(f"Dashboard running at {scheme}://127.0.0.1:{port}")
    print(
        f"playit.gg: tunnel to localhost:{port} (HTTP)"
        if not use_ssl
        else f"playit.gg: tunnel to localhost:{port} (HTTPS)"
    )

    try:
        uvicorn.run(**kwargs)
    except PermissionError:
        if port in (443, 80):
            print(f"Port {port} needs admin rights. Retrying on 8080...", file=sys.stderr)
            kwargs["port"] = 8080
            print(f"Dashboard running at {scheme}://127.0.0.1:8080")
            print("playit.gg: tunnel to localhost:8080")
            uvicorn.run(**kwargs)
        else:
            raise


def cmd_update():
    from app.services.updater import apply_update_sync, check_for_update
    import asyncio

    settings = get_settings()
    print(f"Checking for updates ({settings.github_repo}@{settings.github_branch})…")
    status = asyncio.run(
        check_for_update(settings.github_repo, settings.github_branch, force=True)
    )
    if not status.get("updates_supported"):
        print(status.get("error") or "Updates not supported", file=sys.stderr)
        sys.exit(1)
    if not status.get("update_available"):
        print("Already on the latest build.")
        return
    result = apply_update_sync(settings.github_branch)
    if not result.get("ok"):
        print(result.get("error", "Update failed"), file=sys.stderr)
        sys.exit(1)
    print(f"Updated to {result.get('local_short_sha', 'latest')}.")
    if result.get("restarted"):
        print("Service restarted.")
    elif result.get("restart_required"):
        print("Run: python start.py restart")


def cmd_restart():
    from app.services.restart import restart_from_cli

    result = restart_from_cli()
    if not result.get("ok"):
        print(result.get("error", "Restart failed"), file=sys.stderr)
        sys.exit(1)
    print(result.get("message", "Restarted."))


def cmd_version():
    from app.services.updater import get_local_short_commit

    commit = get_local_short_commit()
    suffix = f" [{commit}]" if commit else ""
    print(f"Personal Dashboard  build {__build__}  (v{__version__}){suffix}")


def main():
    parser = argparse.ArgumentParser(description="Personal Dashboard")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run", "update", "restart", "version"),
        help="run (default), update, restart, or version",
    )
    args = parser.parse_args()
    os.chdir(BASE_DIR)

    if args.command == "run":
        run_server()
    elif args.command == "update":
        cmd_update()
    elif args.command == "restart":
        cmd_restart()
    elif args.command == "version":
        cmd_version()


if __name__ == "__main__":
    main()
