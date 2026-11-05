# Desktop app (Windows)

Local FastAPI + React UI in a pywebview window. Imaginaire uses Chrome CDP on this machine.

## Install

```powershell
cd C:\path\to\mtg-price-checker
python -m pip install -e ".[desktop,browser,dev]"
python -m playwright install chromium
```

Imaginaire’s happy path attaches to **system Chrome via CDP**, so Playwright Chromium is mainly a fallback for other browser modes.

## One-file executable

```powershell
.\build-exe.bat
```

Output: `dist\MTG-Price-Checker.exe` (uses `assets/app.ico`)

Double-click to run. Imaginaire still uses your installed Google Chrome (launched/closed by the app). First launch can be slower while the exe unpacks.

Regenerate the icon:

```powershell
python scripts/generate_app_icon.py
```

Requires Node.js on the build machine (frontend build). The finished `.exe` does not need Node.

## Run from source

```powershell
.\run-app.bat
```

Or:

```powershell
cd web\frontend
npm install
npm run build
cd ..\..
python -m mtg_price_checker.desktop
```

API-only (browser tab):

```powershell
python -m mtg_price_checker.app
```

Then open `http://127.0.0.1:8765/`.

Dev UI with Vite proxy:

```powershell
# terminal 1
python -m mtg_price_checker.app

# terminal 2
cd web\frontend
npm run dev
```

## Imaginaire

1. Enable **Imaginaire** and start a run.
2. The app launches Chrome automatically (port `9222`, profile `~\.mtg-chrome-profile`) if CDP is not already up.
3. Solve Cloudflare in that Chrome window if prompted.
4. When the run finishes (or errors/cancels), Chrome launched by the app is closed automatically.

If Chrome is already running with remote debugging, the app reuses it and does **not** close it.

## Notes

- Server binds to `127.0.0.1` only.
- One price-check job at a time.
- Frontend build output is served from `web/frontend/dist`.
- When a run finishes (success, cancel, or error), Windows shows a toast notification.
