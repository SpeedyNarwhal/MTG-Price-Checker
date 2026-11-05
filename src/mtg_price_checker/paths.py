from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    """Repo root in development, PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def frontend_dist_dir() -> Path:
    return project_root() / "web" / "frontend" / "dist"
