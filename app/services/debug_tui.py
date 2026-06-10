"""Playit-style boxed terminal UI for dashboard debug logs."""

from __future__ import annotations

import os
import shutil
import sys
import time
import urllib.error
import urllib.request

from app.config import BASE_DIR, get_settings
from app.services.debug_log import format_uptime, tail_log_lines, uptime_seconds
from app.services.restart import _read_pid
from app.services.updater import get_local_short_commit
from app.version import __build__, __version__

BOX_TL, BOX_TR, BOX_BL, BOX_BR, BOX_H, BOX_V = "┌", "┐", "└", "┘", "─", "│"


def _term_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size(fallback=(100, 32))
        return max(size.columns, 72), max(size.lines, 24)
    except OSError:
        return 100, 32


def _pad_center(text: str, width: int) -> str:
    inner = max(0, width - 2)
    if len(text) > inner:
        return text[: inner - 1] + "…"
    spaces = max(0, inner - len(text))
    left = spaces // 2
    return " " * left + text + " " * (spaces - left)


def _pad_line(text: str, width: int) -> str:
    inner = max(0, width - 2)
    if len(text) > inner:
        return text[: inner - 1] + "…"
    return text + " " * (inner - len(text))


def _mini_box(width: int, content: str) -> list[str]:
    inner = max(0, width - 2)
    top = BOX_TL + BOX_H * inner + BOX_TR
    body = BOX_V + _pad_line(content, width) + BOX_V
    bot = BOX_BL + BOX_H * inner + BOX_BR
    return [top, body, bot]


def _panel(title: str, lines: list[str], width: int, height: int) -> list[str]:
    inner_w = max(0, width - 2)
    title_bit = f" {title} "
    dash = max(0, inner_w - len(title_bit))
    top = BOX_TL + title_bit + BOX_H * dash + BOX_TR
    out = [top]
    for i in range(height):
        line = lines[i] if i < len(lines) else ""
        out.append(BOX_V + _pad_line(line, width) + BOX_V)
    out.append(BOX_BL + BOX_H * inner_w + BOX_BR)
    return out


def _join_row(boxes: list[list[str]]) -> list[str]:
    if not boxes:
        return []
    rows = len(boxes[0])
    merged = []
    for r in range(rows):
        merged.append("".join(b[r] for b in boxes))
    return merged


def _http_ok(port: int) -> bool:
    for scheme in ("http", "https"):
        url = f"{scheme}://127.0.0.1:{port}/api/status"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            continue
    return False


def _detect_port() -> int | None:
    env_port = os.getenv("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
    for port in (80, 443, 8080):
        if _http_ok(port):
            return port
    return None


def _gather_status() -> dict:
    settings = get_settings()
    port = _detect_port()
    online = port is not None
    pid = _read_pid()
    commit = get_local_short_commit() or "—"
    return {
        "version": f"dashboard v{__version__} (build {__build__})",
        "uptime": format_uptime(uptime_seconds()),
        "status": "● Online" if online else "● Offline",
        "port": str(port) if port else "—",
        "pid": str(pid) if pid else "—",
        "commit": commit,
        "news": "yes" if settings.news_configured else "no",
        "weather": "yes" if settings.owm_configured or settings.wapi_configured else "no",
        "repo": settings.github_repo,
    }


def _status_lines(info: dict, width: int) -> list[str]:
    inner = width - 4
    lines = [
        f"Install: {BASE_DIR}"[:inner],
        f"Git: {info['repo']} @ {info['commit']}"[:inner],
        "",
        "API keys configured:",
        f"  Weather: {info['weather']}    News: {info['news']}",
        "",
        "Endpoints:",
        f"  GET /api/status   GET /api/weather   GET /api/news",
        "",
    ]
    if info["status"].endswith("Offline"):
        lines.append("Dashboard is not responding. Run: python start.py")
    else:
        lines.append(f"Listening on port {info['port']}  (PID {info['pid']})")
    return lines


def _stats_line(info: dict) -> str:
    return (
        f"  Port: {info['port']:<6}"
        f"PID: {info['pid']:<8}"
        f"Build: {__build__:<6}"
        f"News: {info['news']:<5}"
        f"Weather: {info['weather']}"
    )


def render_frame(*, following: bool = True) -> str:
    cols, rows = _term_size()
    info = _gather_status()

    w1 = max(22, cols * 42 // 100)
    w2 = max(18, cols * 29 // 100)
    w3 = cols - w1 - w2
    if w3 < 18:
        w3 = 18

    header = _join_row([
        _mini_box(w1, info["version"]),
        _mini_box(w2, _pad_center(info["uptime"], w2).strip()),
        _mini_box(w3, _pad_center(info["status"], w3).strip()),
    ])

    main_h = max(8, rows - len(header) - 8)
    status_lines = _status_lines(info, cols)
    main = _panel("Dashboard", status_lines, cols, main_h)

    stats = _panel("Statistics", [_stats_line(info)], cols, 1)

    log_h = max(6, rows - len(header) - len(main) - len(stats) - 3)
    log_lines = tail_log_lines(log_h)
    log_title = f"Service Logs ({len(log_lines)})" + (" [following]" if following else "")
    logs = _panel(log_title, log_lines, cols, log_h)

    footer = _pad_center("q Quit", cols)

    parts = header + [""] + main + [""] + stats + [""] + logs + [""] + [footer]
    return "\n".join(parts)


def _clear_screen() -> None:
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


def _poll_key() -> str | None:
    if sys.platform == "win32":
        import msvcrt

        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8", errors="ignore").lower()
            except AttributeError:
                return chr(ch).lower()
        return None

    import select

    if select.select([sys.stdin], [], [], 0)[0]:
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            return ch.lower()
        except (ImportError, OSError, termios.error):
            line = sys.stdin.readline()
            return (line.strip()[:1] or "").lower()
    return None


def _enable_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def run_debug_tui(refresh_sec: float = 1.0) -> None:
    _enable_utf8_stdout()
    if sys.platform != "win32":
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            if termios.tcgetattr(fd)[3] & termios.ICANON:
                pass
        except Exception:
            pass

    print("Starting debug console… (press q to quit)\n")
    time.sleep(0.5)
    try:
        while True:
            _clear_screen()
            try:
                sys.stdout.write(render_frame(following=True))
                sys.stdout.write("\n")
                sys.stdout.flush()
            except UnicodeEncodeError:
                print(render_frame(following=True).encode("ascii", errors="replace").decode())

            deadline = time.time() + refresh_sec
            while time.time() < deadline:
                key = _poll_key()
                if key == "q":
                    _clear_screen()
                    print("Debug console closed.")
                    return
                time.sleep(0.05)
    except KeyboardInterrupt:
        _clear_screen()
        print("Debug console closed.")
