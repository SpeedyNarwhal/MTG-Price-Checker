# MTG Price Checker

Compare Magic: The Gathering singles prices across Canadian stores, then build a shopping list per store.

**Stores:** Danireon · Silver Goblin · Face to Face · Hobbiesville · Imaginaire

---

## Download (Windows)

1. Open the **[latest release](https://github.com/SpeedyNarwhal/MTG-Price-Checker/releases/latest)**
2. Download **`MTG-Price-Checker.exe`**
3. Double-click to run (no install)

Requires [Google Chrome](https://www.google.com/chrome/) if you enable Imaginaire (the app launches/closes Chrome for you).

> Windows may warn that the app is unsigned. Choose **More info** → **Run anyway** if you trust this build.

---

## What it does

1. Pick stores and minimum condition  
2. Paste a decklist  
3. Watch live progress  
4. Review the price matrix (cheapest cells highlighted)  
5. Choose where to buy each card (or **Don't buy**)  
6. Copy per-store shopping lists  

---

## Run from source (optional)

```powershell
python -m pip install -e ".[desktop,browser,dev]"
.\run-app.bat
```

CLI:

```powershell
python -m pip install -e ".[browser,dev]"
mtg-prices cards.txt --stores danireon silvergoblin facetoface hobbiesville
```

Build your own exe:

```powershell
.\build-exe.bat
```

More detail: [DESKTOP.md](DESKTOP.md) · contributor notes: [AGENTS.md](AGENTS.md)
