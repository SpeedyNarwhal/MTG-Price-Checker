# AGENTS.md — MTG Price Checker Project Context

## Project summary

This is a Python terminal-based Magic: The Gathering price checker.

The program takes a text file containing MTG card names, optionally with quantities, and outputs a CSV where:

- Rows are requested cards.
- Columns are supported stores.
- Each cell is either:
  - the lowest in-stock Near Mint price for that card at that store, or
  - a status such as `OUT_OF_STOCK`, `NOT_FOUND`, or `ERROR`.

A pretty UI may be added later, but the current goal is a clean CLI program.

## Supported / planned stores

Current adapter status:

- `danireon`: working.
- `silvergoblin`: working.
- `facetoface`: in progress.
- `imaginaire`: planned later.

Initial target stores:

- https://facetofacegames.com/
- https://imaginaire.com/
- https://silvergoblin.cards/
- https://www.danireon.com/

## Core design principles

Keep the project modular.

Each store must have its own adapter because each store website works differently.

The shared code should not know how each store website works. The shared code should only deal with normalized `StoreQuote` objects.

The architecture should stay roughly:

```text
input card list
→ parse RequestedCard objects
→ store adapters return StoreQuote objects
→ shared price checker chooses lowest NM in-stock quote
→ CSV writer outputs matrix + optional audit CSV
```

Do not put store-specific scraping/parsing logic in the shared price checker.

Do not duplicate lowest-price business logic inside store adapters.

## Important business rules

The final price for a card/store should be:

1. Only Near Mint condition.
2. Only in-stock listings.
3. Cheapest matching listing.
4. If no NM in-stock listing exists but listings were found, return `OUT_OF_STOCK`.
5. If no matching product/listing was found, return `NOT_FOUND`.
6. If the request/parsing fails, return `ERROR`.

Use these statuses:

- `FOUND`
- `OUT_OF_STOCK`
- `NOT_FOUND`
- `AMBIGUOUS`
- `ERROR`

Do not collapse errors into `OUT_OF_STOCK`.

## Existing source layout

Expected structure:

```text
src/mtg_price_checker/
  cli.py

  domain/
    enums.py
    requested_card.py
    store_quote.py
    price_result.py

  input/
    card_normalizer.py
    decklist_parser.py

  output/
    csv_writer.py

  services/
    price_checker.py
    store_registry.py

  stores/
    base.py
    fake.py
    danireon.py
    silvergoblin.py
    facetoface.py

  infra/
    http_client.py
```

Tests live in:

```text
tests/unit/
```

## CLI behavior

The CLI command is:

```powershell
mtg-prices cards.txt --stores danireon silvergoblin facetoface --output output/prices.csv --audit output/audit.csv
```

Useful tuning options should exist or be preserved:

```powershell
--max-products-per-card
--request-delay-seconds
--cache-ttl-hours
--no-cache
```

Typical safe command:

```powershell
mtg-prices cards.txt --stores danireon silvergoblin --output output/prices.csv --audit output/audit.csv
```

Deeper but slower search:

```powershell
mtg-prices cards.txt --stores danireon silvergoblin --max-products-per-card 10 --request-delay-seconds 8 --output output/prices.csv --audit output/audit.csv
```

Fresh run ignoring cache:

```powershell
mtg-prices cards.txt --stores danireon silvergoblin --no-cache --request-delay-seconds 10 --output output/fresh-prices.csv --audit output/fresh-audit.csv
```

## Caching and rate limiting

The project has an HTTP client in `infra/http_client.py`.

Important behavior:

- Use a shared `HttpClient` instance when building multiple real store adapters.
- Respect `request_delay_seconds`.
- Cache successful responses under `.cache/http`.
- Cache TTL should default to 24 hours because store inventory changes daily.
- Do not cache forever.
- `.cache/` must be ignored by Git.
- `/output/` must be ignored by Git, but `src/mtg_price_checker/output/` must be tracked.

Correct `.gitignore` style:

```gitignore
/output/
.cache/
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
dist/
build/
*.egg-info/
.env
```

Do not use `output/` without the leading slash, because that can accidentally ignore `src/mtg_price_checker/output/`.

## Scraping / request safety

Be conservative.

Do not make many rapid requests to store websites.

Avoid retry storms.

If a store returns HTTP 429, do not immediately hit fallback URLs that double the request count.

For example, in a store adapter, if a `.js` or JSON request gets HTTP 429, re-raise the error instead of falling back to HTML and making another request.

Default request delay should be around 8 seconds for live multi-store runs.

## Current known store details

### Danireon

Danireon adapter is working.

Strategy:

```text
/search?q=<card>&type=product
→ extract product URLs
→ open product pages
→ parse condition text such as:
   Near Mint - $1.68 CAD
   Near Mint - Sold out
   Near Mint - $2.23 CAD - sold out!
```

Important details:

- Product URLs may be `/products/...`, `/collections/all/products/...`, or `/collections/mtg-singles/products/...`.
- Do not restrict only to `/collections/mtg-singles/products/`.
- Parser should allow sold-out NM listings with `price_cad = None` if no price is shown.
- Final shared price checker decides `OUT_OF_STOCK`.

### Silver Goblin

Silver Goblin adapter is working.

Strategy:

```text
/search?q=<card>&type=product
→ extract product URLs
→ try Shopify product .js JSON
→ parse variants
→ fallback to HTML only if appropriate
```

Important details:

- Some products have condition-labelled variants like `Near Mint`.
- Some products use a default variant such as `Default Title`; for those, treat the product as NM with lower confidence if it matches the requested card.
- Search result order is not necessarily cheapest.
- `max_products_per_card` matters. For Sol Ring, too small a candidate count may miss the true cheapest NM copy.
- Normal default can be 5; deep mode can use 10+.

### Face to Face

Face to Face adapter is currently in progress.

Important current finding:

- `/search?q=Arcane Signet&type=product` returned irrelevant raw HTML product links like:
  - gift card
  - booster packs
  - Lorcana
  - Pokémon
- So normal `/search` HTML is not reliable for card discovery.

Current intended strategy:

```text
/search/suggest.json?q=<card>&resources[type]=product&resources[limit]=20
→ extract product URLs from JSON
→ open product pages
→ parse NM count and regular price
```

Fallback to `/search` HTML only if suggest JSON gives no usable result.

Face to Face product pages expose useful text such as:

```text
Set: Commander 2020
Type Line: Artifact
Finish: Non-Foil
Collector #: 237
NM (6)
Regular price $1.49
```

Parser should extract:

- card name
- set name
- collector number
- finish
- condition
- quantity
- regular price

Face to Face title strings may look like:

```text
Arcane Signet [237] [Commander 2020] [Non-Foil]
```

Strip bracket suffixes so matched card name becomes:

```text
Arcane Signet
```

Important parser regex note:

Use a condition regex that can match across newlines. This works:

```python
_CONDITION_PATTERN = re.compile(
    r"(?P<label>NM|PL|MP|HP|DMG)\s*"
    r"\((?P<quantity>\d+)\)"
    r"[\s\S]{0,300}?"
    r"Regular price\s+\$(?P<price>\d+(?:\.\d{2})?)",
    re.IGNORECASE,
)
```

Do not use `.{0,300}?` unless `re.DOTALL` is enabled, because test fixtures and real HTML may contain newlines between `NM (6)` and `Regular price`.

Likewise, this set regex is safer:

```python
_SET_PATTERN = re.compile(r"Set:\s*(?P<set_name>[\s\S]+?)\s+Type Line:", re.IGNORECASE)
```

## Important types

`StoreQuote.price_cad` should be:

```python
Decimal | None
```

because sold-out listings may have no visible price.

When choosing the cheapest quote, avoid Pylance issues with `Decimal | None`.

Use a helper like:

```python
def _required_price(quote: StoreQuote) -> Decimal:
    if quote.price_cad is None:
        raise ValueError("Expected quote to have a price.")
    return quote.price_cad
```

Then:

```python
return min(valid_quotes, key=_required_price)
```

Do not use:

```python
return min(valid_quotes, key=lambda quote: quote.price_cad)
```

because Pylance may complain that the key can be `Decimal | None`.

## BeautifulSoup typing notes

BeautifulSoup attribute values can have broad types.

When reading `href`, use:

```python
href_value = link.get("href")

if not isinstance(href_value, str):
    continue
```

Do not pass raw BeautifulSoup attribute values directly to `urljoin`, or Pylance may complain.

## Input file encoding notes

PowerShell can create UTF-16 or BOM-containing text files depending on command/version.

The parser should handle:

- `utf-8-sig`
- `utf-8`
- `utf-16`

The normalizer should strip invisible characters such as:

```python
"\ufeff"  # BOM
"\u200b"  # zero-width space
```

This prevents searching for `﻿Sol Ring` instead of `Sol Ring`.

## Testing commands

Before committing, always run:

```powershell
ruff format .
ruff check . --fix
pytest
```

Useful live smoke tests:

```powershell
Set-Content -Path one-card.txt -Value "Sol Ring" -Encoding utf8

mtg-prices one-card.txt --stores danireon --output output/danireon-one-card.csv --audit output/danireon-one-card-audit.csv

mtg-prices one-card.txt --stores silvergoblin --max-products-per-card 10 --output output/sg-one-card.csv --audit output/sg-one-card-audit.csv
```

Two-store test:

```powershell
Set-Content -Path two-store-test.txt -Value @(
  "Sol Ring",
  "Arcane Signet",
  "Counterspell",
  "Command Tower",
  "Blood Crypt"
) -Encoding utf8

mtg-prices two-store-test.txt --stores danireon silvergoblin --output output/two-store-prices.csv --audit output/two-store-audit.csv
```

Face to Face test:

```powershell
Set-Content -Path one-card.txt -Value "Arcane Signet" -Encoding utf8

mtg-prices one-card.txt --stores facetoface --max-products-per-card 10 --output output/f2f-one-card.csv --audit output/f2f-one-card-audit.csv
```

## Git workflow

Use feature branches:

```powershell
git checkout main
git pull
git checkout -b milestone-name
```

Commit once tests pass:

```powershell
git status
git add .
git commit -m "Clear descriptive message"
git push --set-upstream origin branch-name
```

Merge when stable:

```powershell
git checkout main
git pull
git merge branch-name
git push
```

## Current development plan

Immediate next steps:

1. Finish/debug Face to Face adapter.
2. Confirm Face to Face can find Arcane Signet through suggest JSON.
3. Confirm parser returns NM in-stock price.
4. Test Face to Face on:
   - Sol Ring
   - Arcane Signet
   - Counterspell
   - Command Tower
   - Blood Crypt
5. Test all three stores together.
6. Commit milestone 4.
7. After Face to Face, investigate Imaginaire.

Do not start Imaginaire until Face to Face is stable.

## General guidance for future Codex work

When making changes:

- Keep changes small.
- Preserve existing public behavior unless explicitly changing it.
- Add or update tests for parser changes.
- Prefer parser fixture tests before live tests.
- Do not remove rate limiting or cache TTL.
- Do not hardcode one-off product URLs as the normal strategy.
- Do not make the app browser-automation-based unless all simpler HTTP/JSON options fail.
- If live store behavior differs from tests, update tests to reflect the real HTML/JSON shape.
- Keep audit CSV useful because it is the main debugging tool for store adapters.