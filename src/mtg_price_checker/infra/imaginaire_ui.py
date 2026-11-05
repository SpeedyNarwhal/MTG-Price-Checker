from __future__ import annotations

import random
import time
from typing import Any

from mtg_price_checker.infra.browser_http_client import (
    is_cloudflare_challenge_visible,
    is_cloudflare_challenge_visible_in_html,
    is_deck_builder_interactive_ready,
    is_successful_deck_builder_response,
)
from mtg_price_checker.stores.imaginaire import (
    count_ready_magicdecklist_summaries,
    deck_items_api_to_ui,
)

DECK_BUILDER_URL_FRAGMENT = "constructeur-de-deck"

DECK_INPUT_SELECTORS: tuple[str, ...] = (
    "textarea",
    'input[name="deckItems"]',
    "#deckItems",
)

CONDITION_SELECTORS: tuple[str, ...] = (
    'select[name="condition"]',
    'input[name="condition"]',
)

DECK_BUILDER_SUBMIT_SELECTORS: tuple[str, ...] = (
    "#send2",
    'button[name="send"]',
    "button.action#send2",
    'button:has-text("Créer mon deck")',
)

DECK_BUILDER_AJAX_FRAGMENT = "getDeckBuilder.asp"
DECK_RESULTS_SELECTOR = "li.card-listing"
_CF_STABLE_SECONDS = 3.0
_CF_STABLE_POLL_SECONDS = 0.5
_DOM_RESULTS_POLL_SECONDS = 0.25
_DOM_RESULTS_READY_POLLS = 2
_DOM_RESULTS_STABLE_POLLS = 4
# Longer plateau before accepting fewer listings than pasted (site may omit unknown cards).
_DOM_RESULTS_PARTIAL_STABLE_POLLS = 12


def should_use_browser_ui_post(
    *,
    browser_ui_post: bool | None,
    browser_cdp_url: str | None,
    browser_only: bool,
    browser_headless: bool,
) -> bool:
    if browser_ui_post is not None:
        return browser_ui_post
    if browser_cdp_url is not None:
        return True
    if browser_only and not browser_headless:
        return True
    return False


def is_on_deck_builder_url(url: str) -> bool:
    return DECK_BUILDER_URL_FRAGMENT in url.lower()


def human_pause(min_ms: int, max_ms: int, *, enabled: bool = True) -> None:
    if not enabled:
        return
    time.sleep(random.randint(min_ms, max_ms) / 1000.0)


def find_first_locator(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() > 0:
                return locator
        except Exception:
            continue
    return None


def find_deck_builder_submit_locator(page: Any) -> Any | None:
    for selector in DECK_BUILDER_SUBMIT_SELECTORS:
        locator = page.locator(selector).first
        try:
            if locator.count() > 0 and locator.is_visible():
                return locator
        except Exception:
            continue
    return None


def human_scroll_to(page: Any, locator: Any, *, enabled: bool = True) -> None:
    locator.scroll_into_view_if_needed()
    if not enabled:
        return
    nudge = random.randint(-50, 50)
    if nudge != 0:
        page.mouse.wheel(0, nudge)
    human_pause(150, 350, enabled=enabled)


def human_click(page: Any, locator: Any, *, enabled: bool = True) -> None:
    box = locator.bounding_box()
    if box is not None and enabled:
        x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
        y = box["y"] + box["height"] * random.uniform(0.25, 0.75)
        page.mouse.move(x, y)
        human_pause(80, 200, enabled=enabled)
        page.mouse.click(x, y)
        return
    locator.click()


def human_clear_field(page: Any, locator: Any) -> None:
    human_click(page, locator, enabled=False)
    page.keyboard.press("Control+A")
    human_pause(50, 150, enabled=False)
    page.keyboard.press("Backspace")


def write_clipboard(page: Any, text: str) -> bool:
    try:
        page.evaluate(
            """
            async (value) => {
              await navigator.clipboard.writeText(value);
            }
            """,
            text,
        )
        return True
    except Exception:
        return False


def human_paste(
    page: Any,
    locator: Any,
    text: str,
    *,
    enabled: bool = True,
) -> None:
    human_scroll_to(page, locator, enabled=enabled)
    human_click(page, locator, enabled=enabled)
    human_clear_field(page, locator)
    human_pause(400, 1200, enabled=enabled)

    if write_clipboard(page, text):
        page.keyboard.press("Control+V")
    else:
        page.keyboard.insert_text(text)

    human_pause(150, 400, enabled=enabled)


def set_condition_nm(page: Any, *, enabled: bool = True) -> None:
    locator = find_first_locator(page, CONDITION_SELECTORS)
    if locator is None:
        return

    human_scroll_to(page, locator, enabled=enabled)
    tag_name = locator.evaluate("el => el.tagName.toLowerCase()")
    if tag_name == "select":
        locator.select_option(value="NM")
    elif tag_name == "input":
        input_type = locator.evaluate("el => el.type || ''")
        if input_type in {"radio", "checkbox"}:
            locator.check()
    human_pause(150, 350, enabled=enabled)


def ensure_on_deck_builder_page(page: Any, warmup_url: str, *, navigate: Any) -> None:
    if is_on_deck_builder_url(page.url):
        return
    print(f"Returning to deck builder: {warmup_url}")
    navigate(warmup_url)


def wait_for_cf_stable(
    page: Any,
    *,
    stable_seconds: float = _CF_STABLE_SECONDS,
    timeout_seconds: float = 60.0,
    warmup_url: str | None = None,
    navigate: Any | None = None,
) -> None:
    if is_deck_builder_interactive_ready(page):
        return

    stable_since: float | None = None
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if not is_on_deck_builder_url(page.url) and warmup_url and navigate:
            ensure_on_deck_builder_page(page, warmup_url, navigate=navigate)

        if is_cloudflare_challenge_visible(page):
            stable_since = None
            time.sleep(_CF_STABLE_POLL_SECONDS)
            continue

        if stable_since is None:
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= stable_seconds:
            return

        time.sleep(_CF_STABLE_POLL_SECONDS)

    if warmup_url and navigate and not is_on_deck_builder_url(page.url):
        ensure_on_deck_builder_page(page, warmup_url, navigate=navigate)
        return

    raise RuntimeError("Cloudflare challenge did not stabilize in time.")


def extract_deck_builder_results_html(page: Any) -> str:
    return page.locator(DECK_RESULTS_SELECTOR).evaluate_all(
        "els => els.map(el => el.outerHTML).join('')"
    )


def wait_for_deck_builder_results_html(
    page: Any,
    *,
    timeout_ms: int = 60_000,
    expected_listing_count: int | None = None,
) -> str:
    deadline = time.monotonic() + timeout_ms / 1000.0
    ready_polls = 0
    stable_polls = 0
    last_count = 0
    partial_count = 0

    while time.monotonic() < deadline:
        try:
            locator = page.locator(DECK_RESULTS_SELECTOR)
            count = locator.count()
            if count > 0:
                partial_count = count

                if expected_listing_count is not None:
                    if count >= expected_listing_count:
                        html = extract_deck_builder_results_html(page)
                        _, summaries_ready = count_ready_magicdecklist_summaries(html)
                        if summaries_ready >= expected_listing_count:
                            ready_polls += 1
                            if ready_polls >= _DOM_RESULTS_READY_POLLS:
                                if is_successful_deck_builder_response(html):
                                    print(
                                        "Captured deck builder response from DOM "
                                        f"({count}/{expected_listing_count} listing(s), "
                                        "summaries ready)"
                                    )
                                    return html
                        else:
                            ready_polls = 0
                        stable_polls = 0
                    elif count == last_count and count > 0:
                        html = extract_deck_builder_results_html(page)
                        _, summaries_ready = count_ready_magicdecklist_summaries(html)
                        if summaries_ready >= count and is_successful_deck_builder_response(html):
                            stable_polls += 1
                            if stable_polls >= _DOM_RESULTS_PARTIAL_STABLE_POLLS:
                                print(
                                    "Captured deck builder response from DOM "
                                    f"({count}/{expected_listing_count} listing(s); "
                                    "site omitted some cards)"
                                )
                                return html
                        else:
                            stable_polls = 0
                    else:
                        ready_polls = 0
                        stable_polls = 0
                        last_count = count
                elif count == last_count:
                    stable_polls += 1
                    if stable_polls >= _DOM_RESULTS_STABLE_POLLS:
                        html = extract_deck_builder_results_html(page)
                        if is_successful_deck_builder_response(html):
                            print(f"Captured deck builder response from DOM ({count} listing(s))")
                            return html
                else:
                    stable_polls = 0
                    last_count = count
        except Exception:
            ready_polls = 0
            stable_polls = 0

        time.sleep(_DOM_RESULTS_POLL_SECONDS)

    if partial_count > 0:
        html = extract_deck_builder_results_html(page)
        if is_successful_deck_builder_response(html):
            expected = str(expected_listing_count) if expected_listing_count is not None else "?"
            print(
                "Captured deck builder response from DOM after timeout "
                f"({partial_count}/{expected} listing(s))"
            )
            return html

    raise RuntimeError(
        "Deck builder results did not appear after submit. "
        "Check the browser tab for errors or an empty deck list."
    )


def submit_and_capture_response(
    page: Any,
    submit_locator: Any,
    *,
    ajax_fragment: str = DECK_BUILDER_AJAX_FRAGMENT,
    timeout_ms: int = 60_000,
    prefer_dom_capture: bool = False,
    expected_listing_count: int | None = None,
) -> str:
    if prefer_dom_capture:
        human_click(page, submit_locator)
        return wait_for_deck_builder_results_html(
            page,
            timeout_ms=timeout_ms,
            expected_listing_count=expected_listing_count,
        )

    try:
        with page.expect_response(
            lambda response: ajax_fragment in response.url and response.request.method == "POST",
            timeout=timeout_ms,
        ) as response_info:
            human_click(page, submit_locator)

        response = response_info.value
    except Exception as exc:
        if not is_on_deck_builder_url(page.url):
            raise DeckBuilderNavigationError(
                f"Page navigated away from deck builder ({page.url}). "
                "Wrong submit button may have been clicked."
            ) from exc
        raise

    status = response.status
    if status < 200 or status >= 300:
        raise RuntimeError(f"Deck builder POST failed with status {status}.")

    try:
        html = response.text()
    except Exception:
        return wait_for_deck_builder_results_html(
            page,
            timeout_ms=timeout_ms,
            expected_listing_count=expected_listing_count,
        )

    print("Captured deck builder response from XHR")
    return html


def post_deck_builder_via_ui(
    page: Any,
    *,
    deck_items_api: str,
    condition: str = "NM",
    ajax_url: str,
    warmup_url: str | None,
    human_delays: bool = True,
    is_on_deck_builder: bool,
    navigate: Any,
    prefer_dom_capture: bool = False,
) -> str:
    del condition

    deck_items_ui = deck_items_api_to_ui(deck_items_api)
    card_count = len([line for line in deck_items_ui.splitlines() if line.strip()])
    print(f"UI paste mode: {card_count} card(s), newline format")

    if warmup_url is not None and not is_on_deck_builder:
        print(f"Navigating to deck builder: {warmup_url}")
        navigate(warmup_url)

    print("Waiting for Cloudflare to stabilize...")
    wait_for_cf_stable(
        page,
        warmup_url=warmup_url,
        navigate=navigate,
    )

    deck_input = find_first_locator(page, DECK_INPUT_SELECTORS)
    if deck_input is None:
        raise RuntimeError("Could not find Imaginaire deck input field on the page.")

    print("Pasting deck list into textarea...")
    human_paste(page, deck_input, deck_items_ui, enabled=human_delays)
    set_condition_nm(page, enabled=human_delays)

    submit = find_deck_builder_submit_locator(page)
    if submit is None:
        raise RuntimeError("Could not find deck builder submit button (#send2 / Créer mon deck).")

    human_scroll_to(page, submit, enabled=human_delays)
    human_pause(200, 500, enabled=human_delays)

    print('Clicking deck builder submit (#send2 / "Créer mon deck")...')
    try:
        html = submit_and_capture_response(
            page,
            submit,
            ajax_fragment=ajax_url.rsplit("/", 1)[-1],
            prefer_dom_capture=prefer_dom_capture,
            expected_listing_count=card_count,
        )
    except DeckBuilderNavigationError:
        if warmup_url is None:
            raise
        print("Wrong page after submit; returning to deck builder and retrying once...")
        navigate(warmup_url)
        wait_for_cf_stable(page, warmup_url=warmup_url, navigate=navigate)
        deck_input = find_first_locator(page, DECK_INPUT_SELECTORS)
        if deck_input is None:
            raise RuntimeError("Could not find deck input after recovery navigation.") from None
        human_paste(page, deck_input, deck_items_ui, enabled=human_delays)
        submit = find_deck_builder_submit_locator(page)
        if submit is None:
            raise RuntimeError("Could not find #send2 after recovery navigation.") from None
        html = submit_and_capture_response(
            page,
            submit,
            ajax_fragment=ajax_url.rsplit("/", 1)[-1],
            prefer_dom_capture=prefer_dom_capture,
            expected_listing_count=card_count,
        )

    if is_cloudflare_challenge_visible_in_html(html):
        raise CloudflareBlockedResponseError(
            "Deck builder response looks like a Cloudflare challenge."
        )

    if not is_successful_deck_builder_response(html):
        raise RuntimeError("Deck builder response did not contain expected card listings.")

    print(f"Captured deck builder response ({len(html):,} chars)")
    return html


class CloudflareBlockedResponseError(RuntimeError):
    pass


class DeckBuilderNavigationError(RuntimeError):
    pass
