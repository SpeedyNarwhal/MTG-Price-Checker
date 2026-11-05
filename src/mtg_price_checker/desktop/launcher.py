from __future__ import annotations

import socket
import threading
import time

import uvicorn

from mtg_price_checker.app.api import create_app

_HOST = "127.0.0.1"


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
    port = _free_port()
    app = create_app()
    config = uvicorn.Config(app, host=_HOST, port=port, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(_HOST, port)

    url = f"http://{_HOST}:{port}/"

    try:
        import webview

        window = webview.create_window(
            "MTG Price Checker",
            url=url,
            width=1280,
            height=860,
            min_size=(960, 640),
        )
        webview.start()
        _ = window
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
