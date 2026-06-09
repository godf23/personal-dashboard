#!/usr/bin/env python3
"""Start the personal dashboard for local use or playit.gg tunneling."""

import os
import socket
import sys

import uvicorn

from app.config import get_settings

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


def main():
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

    print(f"Dashboard running at {scheme}://127.0.0.1:{port}")
    print(f"playit.gg: tunnel to localhost:{port} (HTTP)" if not use_ssl else f"playit.gg: tunnel to localhost:{port} (HTTPS)")

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


if __name__ == "__main__":
    main()
