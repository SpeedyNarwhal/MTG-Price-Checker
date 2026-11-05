from __future__ import annotations

import sys
from pathlib import Path


def notify_job_finished(*, title: str, message: str) -> None:
    """Show a Windows toast when a price-check job finishes. No-op on failure/non-Windows."""
    if sys.platform != "win32":
        return

    try:
        from winotify import Notification, audio
    except ImportError:
        return

    try:
        kwargs: dict[str, object] = {
            "app_id": "MTG Price Checker",
            "title": title,
            "msg": message,
            "duration": "short",
        }
        icon = _app_icon_path()
        if icon is not None:
            kwargs["icon"] = str(icon)

        toast = Notification(**kwargs)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        # Notifications must never break the price-check run.
        return


def _app_icon_path() -> Path | None:
    try:
        from mtg_price_checker.paths import project_root

        candidate = project_root() / "assets" / "app.ico"
        if candidate.is_file():
            return candidate
    except Exception:
        return None
    return None
