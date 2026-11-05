# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "web" / "frontend" / "dist"), "web/frontend/dist"),
    (str(ROOT / "assets" / "app.ico"), "assets"),
]
binaries: list = []
hiddenimports = [
    "mtg_price_checker",
    "mtg_price_checker.app",
    "mtg_price_checker.app.api",
    "mtg_price_checker.app.jobs",
    "mtg_price_checker.app.imaginaire_chrome",
    "mtg_price_checker.desktop",
    "mtg_price_checker.desktop.launcher",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "playwright",
    "playwright.sync_api",
    "webview",
    "bottle",
]

for package in ("uvicorn", "fastapi", "starlette", "anyio", "webview"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("mtg_price_checker")

a = Analysis(
    [str(ROOT / "src" / "mtg_price_checker" / "desktop" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MTG-Price-Checker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
)
