from __future__ import annotations

import argparse
from pathlib import Path

from mtg_price_checker.infra.browser_http_client import playwright_cookies_from_file
from mtg_price_checker.infra.http_client import HttpClient, HttpClientConfig
from mtg_price_checker.infra.imaginaire_http_client import ImaginaireHttpClient
from mtg_price_checker.infra.impersonating_http_client import ImpersonatingHttpClient
from mtg_price_checker.services.store_registry import _DEFAULT_IMAGINAIRE_PROFILE_DIR

DECK_BUILDER_AJAX_URL = "https://imaginaire.com/ajax/getDeckBuilder.asp"
DEFAULT_REFERER = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"


def _format_deck_items(card_names: list[str]) -> str:
    return " | ".join(f"${name.strip().lower()}" for name in card_names if name.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Probe Imaginaire deck builder endpoint. "
            "Recommended CDP setup: start Chrome with --remote-debugging-port=9222, "
            "solve CF on the deck builder page, then run with --browser-cdp-url."
        ),
    )
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help=(
            "Optional Netscape cookies file. cf_clearance is skipped for Playwright "
            "(prefer persistent profile or CDP instead)."
        ),
    )
    parser.add_argument(
        "--plain-http",
        action="store_true",
        help="Use plain requests HttpClient (expected to fail behind Cloudflare).",
    )
    parser.add_argument(
        "--browser-only",
        action="store_true",
        help="Use Playwright only (skip curl_cffi TLS impersonation).",
    )
    parser.add_argument(
        "--browser-headed",
        action="store_true",
        help="Run Playwright in headed mode for manual Cloudflare verification.",
    )
    parser.add_argument(
        "--browser-manual-cf",
        action="store_true",
        help="Press Enter when deck builder is ready (headed mode).",
    )
    parser.add_argument(
        "--browser-cdp-url",
        default=None,
        help="Connect to existing Chrome via CDP (e.g. http://127.0.0.1:9222).",
    )
    parser.add_argument(
        "--browser-ui-post",
        action="store_true",
        help="Paste deck list via UI and click submit (default on for CDP/headed).",
    )
    parser.add_argument(
        "--no-browser-ui-post",
        action="store_true",
        help="Force legacy in-page fetch POST instead of UI automation.",
    )
    parser.add_argument(
        "--browser-profile-dir",
        type=Path,
        default=None,
        help=f"Persistent browser profile directory (default: {_DEFAULT_IMAGINAIRE_PROFILE_DIR}).",
    )
    parser.add_argument(
        "--tls-only",
        action="store_true",
        help="Use curl_cffi ImpersonatingHttpClient only (no Playwright fallback).",
    )
    args = parser.parse_args()

    cards = ["Sol Ring", "Arcane Signet", "Counterspell"]
    deck_items = _format_deck_items(cards)
    form = {
        "deckItems": deck_items,
        "foil": "",
        "condition": "NM",
        "sitelist": "",
    }

    profile_dir = (
        None
        if args.browser_cdp_url
        else (args.browser_profile_dir or _DEFAULT_IMAGINAIRE_PROFILE_DIR)
    )

    browser_ui_post: bool | None = None
    if args.no_browser_ui_post:
        browser_ui_post = False
    elif args.browser_ui_post:
        browser_ui_post = True

    config = HttpClientConfig(
        min_seconds_between_requests=0.0,
        warmup_hosts=args.plain_http,
        use_cache=False,
        cookies_file=args.cookies_file,
        browser_headless=not args.browser_headed,
        browser_only=args.browser_only,
        browser_manual_cf=args.browser_manual_cf,
        browser_cdp_url=args.browser_cdp_url,
        browser_ui_post=browser_ui_post,
        browser_profile_dir=profile_dir,
        cloudflare_warmup_url=DEFAULT_REFERER,
    )

    if args.cookies_file is not None and args.cookies_file.exists():
        _, skipped_cf = playwright_cookies_from_file(args.cookies_file)
        print(f"Cookies file: {args.cookies_file} (will skip {skipped_cf} Cloudflare cookie(s))")
    elif args.cookies_file is not None:
        print(f"Cookies file not found: {args.cookies_file}")

    if args.browser_cdp_url:
        print(f"CDP URL: {args.browser_cdp_url}")
        print(
            "CDP Cloudflare: solve in Chrome; the script proceeds when #send2 and the "
            "deck input are visible, or will ask you to press Enter in this terminal."
        )
    elif not args.plain_http and not args.tls_only:
        print(f"Browser profile: {profile_dir.resolve()}")
        print("Reset profile if stuck: Remove-Item -Recurse -Force .cache\\browser\\imaginaire")

    from mtg_price_checker.infra.imaginaire_ui import should_use_browser_ui_post

    ui_post = should_use_browser_ui_post(
        browser_ui_post=browser_ui_post,
        browser_cdp_url=args.browser_cdp_url,
        browser_only=args.browser_only,
        browser_headless=not args.browser_headed,
    )
    print(f"UI paste mode: {'on' if ui_post else 'off'}")

    if args.plain_http:
        transport = "plain HttpClient"
        http = HttpClient(config)
    elif args.tls_only:
        transport = "ImpersonatingHttpClient (curl_cffi)"
        http = ImpersonatingHttpClient(config)
    else:
        transport = "ImaginaireHttpClient (default)"
        http = ImaginaireHttpClient(config)

    print(f"Transport: {transport}")
    print(f"POST {DECK_BUILDER_AJAX_URL}")
    print(f"deckItems={deck_items}")

    try:
        html = http.post_form(DECK_BUILDER_AJAX_URL, form, referer=DEFAULT_REFERER)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc!r}")
        raise
    finally:
        if hasattr(http, "close"):
            http.close()

    print(f"Response length: {len(html):,} chars")
    for card in cards:
        found = card.lower() in html.lower()
        print(f'Contains "{card}": {found}')

    print("\nFirst 400 chars:\n")
    print(html[:400])


if __name__ == "__main__":
    main()
