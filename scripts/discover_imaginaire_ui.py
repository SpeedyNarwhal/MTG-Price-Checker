from __future__ import annotations

import argparse
from pathlib import Path

from mtg_price_checker.infra.browser_http_client import (
    is_cloudflare_challenge_visible,
    is_deck_builder_ready,
)
from mtg_price_checker.infra.http_client import HttpClientConfig
from mtg_price_checker.infra.imaginaire_ui import (
    CONDITION_SELECTORS,
    DECK_BUILDER_SUBMIT_SELECTORS,
    DECK_INPUT_SELECTORS,
    find_deck_builder_submit_locator,
    find_first_locator,
)
from mtg_price_checker.services.store_registry import _DEFAULT_IMAGINAIRE_PROFILE_DIR

DEFAULT_WARMUP = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"


def _describe_locator(page, selector: str) -> str:
    locator = page.locator(selector).first
    try:
        count = locator.count()
    except Exception as exc:
        return f"{selector}: error ({exc})"
    if count == 0:
        return f"{selector}: not found"
    try:
        visible = locator.is_visible()
        tag = locator.evaluate("el => el.tagName")
        name = locator.evaluate("el => el.getAttribute('name') || ''")
        id_attr = locator.evaluate("el => el.getAttribute('id') || ''")
        return (
            f"{selector}: count={count}, visible={visible}, "
            f"tag={tag}, name={name!r}, id={id_attr!r}"
        )
    except Exception as exc:
        return f"{selector}: count={count}, detail error ({exc})"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Imaginaire deck builder UI selectors. "
            "Connect via CDP after solving Cloudflare, or use headed profile."
        ),
    )
    parser.add_argument(
        "--browser-cdp-url",
        default=None,
        help="Connect to existing Chrome via CDP (e.g. http://127.0.0.1:9222).",
    )
    parser.add_argument(
        "--browser-headed",
        action="store_true",
        help="Run Playwright in headed mode.",
    )
    parser.add_argument(
        "--browser-profile-dir",
        type=Path,
        default=None,
        help=f"Persistent browser profile (default: {_DEFAULT_IMAGINAIRE_PROFILE_DIR}).",
    )
    args = parser.parse_args()

    profile_dir = (
        None
        if args.browser_cdp_url
        else (args.browser_profile_dir or _DEFAULT_IMAGINAIRE_PROFILE_DIR)
    )

    config = HttpClientConfig(
        min_seconds_between_requests=0.0,
        use_cache=False,
        browser_headless=not args.browser_headed,
        browser_cdp_url=args.browser_cdp_url,
        browser_profile_dir=profile_dir,
        cloudflare_warmup_url=DEFAULT_WARMUP,
    )

    from mtg_price_checker.infra.browser_http_client import BrowserHttpClient

    client = BrowserHttpClient(config)
    try:
        client._ensure_page()
        page = client._page

        if not client._is_on_deck_builder_page():
            print(f"Navigating to {DEFAULT_WARMUP}")
            page.goto(DEFAULT_WARMUP, wait_until="domcontentloaded")

        print(f"URL: {page.url}")
        print(f"Cloudflare challenge visible: {is_cloudflare_challenge_visible(page)}")
        print(f"Deck builder ready: {is_deck_builder_ready(page)}")
        print()

        print("=== Deck input selectors ===")
        for selector in DECK_INPUT_SELECTORS:
            print(_describe_locator(page, selector))
        found_deck = find_first_locator(page, DECK_INPUT_SELECTORS)
        print(f"First match: {found_deck is not None}")
        print()

        print("=== Condition selectors ===")
        for selector in CONDITION_SELECTORS:
            print(_describe_locator(page, selector))
        print()

        print("=== Deck builder submit (#send2) ===")
        for selector in DECK_BUILDER_SUBMIT_SELECTORS:
            print(_describe_locator(page, selector))
        found_submit = find_deck_builder_submit_locator(page)
        print(f"Deck builder submit found: {found_submit is not None}")
        print()

        print("=== Results markers ===")
        for selector in ("li.card-listing", "h3.magictitle", "div.magicdecklist"):
            print(_describe_locator(page, selector))
        decklist = page.locator("div.magicdecklist").first
        try:
            if decklist.count() > 0:
                sample = decklist.evaluate("el => el.outerHTML")
                preview = sample[:800] if len(sample) > 800 else sample
                print(f"\nmagicdecklist sample (first 800 chars):\n{preview}")
        except Exception as exc:
            print(f"magicdecklist sample error: {exc}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
