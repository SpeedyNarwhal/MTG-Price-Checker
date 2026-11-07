from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

from mtg_price_checker.app.api import create_app
from mtg_price_checker.desktop.bridge import DesktopApi
from mtg_price_checker.paths import project_root

_HOST = "127.0.0.1"


def _app_icon_path() -> str | None:
    candidate = project_root() / "assets" / "app.ico"
    if candidate.is_file():
        return str(candidate)
    # Dev runs: assets live at repo root, not under src/
    repo_candidate = Path(__file__).resolve().parents[3] / "assets" / "app.ico"
    if repo_candidate.is_file():
        return str(repo_candidate)
    return None


def _ensure_stdio() -> None:
    """PyInstaller windowed builds set stdout/stderr to None; uvicorn needs them."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_HOST, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(host: str, port: int, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server did not start on {host}:{port}")


def run_desktop_app(*, open_browser_fallback: bool = True) -> None:
    _ensure_stdio()
    port = _free_port()
    app = create_app()
    config = uvicorn.Config(
        app,
        host=_HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(_HOST, port)

    url = f"http://{_HOST}:{port}/"

    try:
        import webview

        # Blob / <a download> clicks are ignored unless downloads are enabled;
        # Excel export still uses the native Save As bridge below.
        webview.settings["ALLOW_DOWNLOADS"] = True

        api = DesktopApi()
        window_kwargs: dict = {
            "title": "MTG Price Checker",
            "url": url,
            "width": 1280,
            "height": 860,
            "min_size": (960, 640),
            "js_api": api,
        }
        icon_path = _app_icon_path()
        if icon_path is not None:
            # Supported on some pywebview backends; ignored if unsupported.
            window_kwargs["icon"] = icon_path
        try:
            window = webview.create_window(**window_kwargs)
        except TypeError:
            window_kwargs.pop("icon", None)
            window = webview.create_window(**window_kwargs)
        api.set_window(window)
        webview.start()
    except Exception as exc:
        if not open_browser_fallback:
            raise

        import webbrowser

        print(f"pywebview unavailable ({exc}); opening {url} in your browser.")
        webbrowser.open(url)
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def main(argv: list[str] | None = None) -> None:
    _ = argv
    run_desktop_app()


if __name__ == "__main__":
    main()
