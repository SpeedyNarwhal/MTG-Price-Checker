from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

_DEFAULT_CDP_URL = "http://127.0.0.1:9222"
_DEFAULT_CDP_PORT = 9222
_DEFAULT_PROFILE_DIR = Path.home() / ".mtg-chrome-profile"
_DECK_BUILDER_URL = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"

_CHROME_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
)

_lock = threading.Lock()
_managed_process: subprocess.Popen[bytes] | None = None
_managed_cdp_url: str | None = None


@dataclass(frozen=True)
class ChromeSession:
    cdp_url: str
    launched_by_app: bool
    chrome_path: str | None = None
    user_data_dir: str | None = None


def default_cdp_url() -> str:
    return _DEFAULT_CDP_URL


def find_chrome_executable() -> Path | None:
    for candidate in _CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def cdp_status(cdp_url: str = _DEFAULT_CDP_URL) -> dict[str, object]:
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        response = requests.get(version_url, timeout=2)
        response.raise_for_status()
        payload = response.json()
        return {
            "reachable": True,
            "cdp_url": cdp_url,
            "browser": payload.get("Browser"),
            "web_socket_debugger_url": payload.get("webSocketDebuggerUrl"),
        }
    except Exception as exc:
        return {
            "reachable": False,
            "cdp_url": cdp_url,
            "error": str(exc),
        }


def wait_for_cdp(
    cdp_url: str = _DEFAULT_CDP_URL,
    *,
    timeout_seconds: float = 60.0,
    poll_seconds: float = 0.5,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    last_status: dict[str, object] = cdp_status(cdp_url)
    while time.time() < deadline:
        last_status = cdp_status(cdp_url)
        if last_status.get("reachable"):
            return last_status
        time.sleep(poll_seconds)
    raise TimeoutError(
        f"Chrome CDP did not become reachable at {cdp_url} within {timeout_seconds:.0f}s."
    )


def launch_chrome_for_imaginaire(
    *,
    cdp_port: int = _DEFAULT_CDP_PORT,
    profile_dir: Path | None = None,
    open_deck_builder: bool = True,
) -> dict[str, object]:
    global _managed_process, _managed_cdp_url

    chrome = find_chrome_executable()
    if chrome is None:
        raise FileNotFoundError(
            "Could not find Google Chrome. Install Chrome or start it manually with "
            "--remote-debugging-port=9222."
        )

    user_data_dir = profile_dir or _DEFAULT_PROFILE_DIR
    user_data_dir.mkdir(parents=True, exist_ok=True)
    cdp_url = f"http://127.0.0.1:{cdp_port}"

    args = [
        str(chrome),
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={user_data_dir}",
    ]
    if open_deck_builder:
        args.append(_DECK_BUILDER_URL)

    process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with _lock:
        _managed_process = process
        _managed_cdp_url = cdp_url

    return {
        "launched": True,
        "launched_by_app": True,
        "chrome_path": str(chrome),
        "user_data_dir": str(user_data_dir),
        "cdp_url": cdp_url,
        "deck_builder_url": _DECK_BUILDER_URL if open_deck_builder else None,
        "pid": process.pid,
    }


def ensure_chrome_for_imaginaire(
    *,
    cdp_url: str | None = None,
    cdp_port: int = _DEFAULT_CDP_PORT,
    timeout_seconds: float = 60.0,
) -> ChromeSession:
    """Reuse an existing CDP Chrome if reachable; otherwise launch and wait."""
    target_url = cdp_url or f"http://127.0.0.1:{cdp_port}"
    status = cdp_status(target_url)
    if status.get("reachable"):
        return ChromeSession(cdp_url=target_url, launched_by_app=False)

    launched = launch_chrome_for_imaginaire(cdp_port=cdp_port, open_deck_builder=True)
    try:
        wait_for_cdp(target_url, timeout_seconds=timeout_seconds)
    except Exception:
        close_managed_chrome()
        raise
    return ChromeSession(
        cdp_url=str(launched["cdp_url"]),
        launched_by_app=True,
        chrome_path=str(launched.get("chrome_path")),
        user_data_dir=str(launched.get("user_data_dir")),
    )


def close_managed_chrome() -> dict[str, object]:
    """Close Chrome only if this app launched it for Imaginaire."""
    global _managed_process, _managed_cdp_url

    with _lock:
        process = _managed_process
        cdp_url = _managed_cdp_url
        _managed_process = None
        _managed_cdp_url = None

    if process is None:
        return {"closed": False, "reason": "no_managed_chrome"}

    if process.poll() is not None:
        return {"closed": False, "reason": "already_exited", "cdp_url": cdp_url}

    _kill_process_tree(process)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass

    return {"closed": True, "cdp_url": cdp_url, "pid": process.pid}


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
