# AGENTS.md

## Project Overview

MTG Price Checker is a terminal-based Python application that compares Magic: The Gathering card prices across multiple Canadian game stores.

Input:

- A text file containing card names (one per line)

Output:

- A CSV matrix:

  - rows = cards
  - columns = stores
  - cell = lowest Near Mint in-stock CAD price OR status indicator

A second audit CSV provides debugging and traceability details:

- status
- chosen product URL
- notes/errors

The project is intentionally modular so new stores can be added independently.

---

# Current Supported Stores

Implemented:

- Danireon
- Silver Goblin
- Face to Face Games

Planned:

- Imaginaire

---

# High-Level Architecture

```text
src/mtg_price_checker/
├── cli.py
├── models/
├── stores/
├── services/
├── infra/
├── input/
├── output/
└── tests/
```

## Important Modules

### `stores/`

Contains one adapter per store.

Each store has completely custom parsing logic because every website behaves differently.

Current adapters:

- `danireon.py`
- `silvergoblin.py`
- `facetoface.py`

### `services/price_checker.py`

Shared orchestration logic:

- loops through stores/cards
- selects lowest valid quote
- handles statuses
- now contains store circuit-breaker logic

### `infra/http_client.py`

Shared HTTP infrastructure:

- request delay
- caching
- cache TTL
- JSON/text helpers
- POST JSON support

### `models/`

Shared domain models:

- `RequestedCard`
- `StoreQuote`
- `PriceResult`
- enums for:

  - condition
  - finish
  - result status

---

# Core Business Rules

## Valid Quote Selection

The app only considers:

- Near Mint (`NM`)
- in-stock
- CAD prices

The final selected result per store/card is:

- lowest valid NM in-stock price

## Status Semantics

### `FOUND`

At least one valid NM in-stock quote exists.

### `OUT_OF_STOCK`

Card exists at the store but no valid NM in-stock quote exists.

### `NOT_FOUND`

No matching product/card found.

### `ERROR`

HTTP errors, parsing failures, unexpected response shapes, etc.

---

# Current Store Implementations

# Danireon

Strategy:

1. Search page request:
   `/search?q=...&type=product`
2. Parse product URLs from HTML
3. Visit product pages
4. Parse condition/price/inventory

Notes:

- Uses Shopify-style product pages
- Previously hit 429 rate limits
- Now uses:

  - cache
  - request delay
  - product limit
- Recently began returning some 403 responses

---

# Silver Goblin

Strategy:

1. Search page request
2. Parse product URLs
3. Visit product pages
4. Parse embedded product JSON
5. Parse variants for:

   - condition
   - price
   - inventory

Notes:

- Product JSON parsing works well
- Correctly finds lowest NM variant
- Recently began returning some 403 responses

---

# Face to Face Games

IMPORTANT:
Face to Face no longer uses HTML search scraping.

It now uses the Deck Builder JSON endpoint.

## Endpoint

```text
POST https://facetofacegames.com/apps/prod-indexer/deckBuilder/search
```

## Payload Shape

```json
{
  "sort": false,
  "filters": [
    {
      "field": "Card Name",
      "values": ["Sol Ring", "Arcane Signet"]
    },
    {
      "field": "in_stock",
      "values": ["1"]
    }
  ]
}
```

## Response Shape

Useful data is under:

```json
{
  "Cards": {
    "Sol Ring": [...],
    "Arcane Signet": [...]
  }
}
```

Each product entry contains:

- `_source.handle`
- `_source.General_Card_Name`
- `_source.MTG_Set_Name`
- `_source.MTG_Collector_Number`
- `_source.MTG_Foil_Option`
- `_source.variants`

Each variant contains:

- `price`
- `inventoryQuantity`
- `selectedOptions`

Condition is found in:

- `selectedOptions`
- option name `"Condition"`

## Batch Preload Architecture

Face to Face supports batch loading.

It should:

- make ONE POST request for the full card list
- preload all results
- store quotes internally

`search_card()` should:

- read from preloaded data
- not make one POST per card during normal runs

This is implemented via:

- optional preload/batch adapter behavior
- preload call before card/store loops

This dramatically improves:

- speed
- request count
- reliability

---

# HTTP Infrastructure

## Shared HttpClient Features

The app uses a shared HTTP client.

Features:

- request delay
- caching
- retry behavior
- GET text helper
- GET JSON helper
- POST JSON helper

## Cache

Cache entries currently expire after:

- 24 hours

Reason:
Store inventory updates daily.

## Request Delay

The app intentionally spaces requests to avoid hammering stores.

CLI tuning options exist for:

- request delay
- max products per card

---

# Important Reliability Features

# Store Circuit Breaker

The app now disables stores during a run after:

- HTTP 403
- HTTP 429

Reason:
Avoid repeatedly hammering a blocked/rate-limited store.

Behavior:

- first 403/429:

  - current request becomes ERROR
  - store disabled for remainder of run
- subsequent cards:

  - store is skipped
  - ERROR returned immediately

Other stores continue normally.

---

# HTTP Headers

The project moved away from a clearly bot-like User-Agent.

The shared HttpClient should use browser-like headers:

- User-Agent
- Accept
- Accept-Language

We could try:

- copy browser cookies
- use proxies
- bypass CAPTCHAs
- attempt anti-bot evasion

Since if other implementations aren't working.

---

# CLI Features

Current CLI supports:

- input file
- output CSV
- audit CSV
- selected stores
- request delay tuning
- max products per card

Example:

```powershell
mtg-prices cards.txt `
  --stores danireon silvergoblin facetoface `
  --request-delay-seconds 8 `
  --max-products-per-card 5 `
  --output output/prices.csv `
  --audit output/audit.csv
```

---

# Testing

The project uses pytest.

Important tests:

- parser tests per store
- Face to Face batch preload tests
- circuit breaker tests
- quote selection tests

Always run before commit:

```powershell
ruff format .
ruff check . --fix
pytest
```

---

# Development Guidelines

## Design Philosophy

Keep:

- store-specific parsing isolated
- shared business logic centralized
- HTTP infrastructure reusable
- adapters modular

## When Adding New Stores

Preferred order of strategies:

1. Official/public JSON endpoint
2. Search endpoint returning structured JSON
3. Embedded product JSON
4. HTML scraping
5. If nothing else works:
- browser automation
- Playwright/Selenium unless absolutely necessary
- copying cookies
- anti-bot bypass techniques

## Desired Future Improvements

Potential future milestones:

- Imaginaire adapter
- async request pipeline
- better fuzzy card matching
- Scryfall metadata integration
- pretty UI/web frontend
- deck import formats
- price history
- buy optimization across stores

---

# Known Current Situation

Face to Face:

- stable
- fastest adapter
- batch endpoint

Danireon / Silver Goblin:

- functional historically
- currently sometimes returning 403
- likely sensitive to request headers and/or scraping patterns

The project now includes:

- browser-like headers
- request throttling
- 24h cache TTL
- circuit breaker protections

---

# Manual Smoke Tests

## Face to Face

```powershell
Set-Content -Path f2f-test.txt -Value @(
  "Sol Ring",
  "Arcane Signet",
  "Counterspell"
) -Encoding utf8

mtg-prices f2f-test.txt `
  --stores facetoface `
  --output output/f2f-prices.csv `
  --audit output/f2f-audit.csv
```

## Multi-store

```powershell
Set-Content -Path three-store-test.txt -Value @(
  "Sol Ring",
  "Arcane Signet",
  "Counterspell",
  "Command Tower",
  "Blood Crypt"
) -Encoding utf8

mtg-prices three-store-test.txt `
  --stores danireon silvergoblin facetoface `
  --request-delay-seconds 8 `
  --max-products-per-card 5 `
  --output output/three-store-prices.csv `
  --audit output/three-store-audit.csv
```
