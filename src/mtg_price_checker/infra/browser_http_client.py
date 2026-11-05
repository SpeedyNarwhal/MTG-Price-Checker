from __future__ import annotations

import re
import time
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from mtg_price_checker.infra.http_client import HttpClientConfig

_CLOUDFLARE_CHALLENGE_TEXT = "Chargement en cours"
_CLOUDFLARE_VERIFY_PATTERNS = (
    re.compile(r"verify you are human", re.IGNORECASE),
    re.compile(r"verifying you are human", re.IGNORECASE),
)
_HEADLESS_CF_TIMEOUT_SECONDS = 60
_HEADED_CF_TIMEOUT_SECONDS = 300
_COOKIE_BASE_URL = "https://imaginaire.com"
_SKIP_BROWSER_COOKIE_NAMES = frozenset({"cf_clearance", "__cf_bm"})
_CLOUDFLARE_COOKIE_NAMES = frozenset({"cf_clearance", "__cf_bm"})
_STEALTH_LAUNCH_ARGS = ("--disable-blink-features=AutomationControlled",)
_STEALTH_IGNORE_DEFAULT_ARGS = ("--enable-automation",)
_DECK_BUILDER_URL_FRAGMENT = "constructeur-de-deck"


class BrowserHttpClient:
    """Playwright-backed HTTP client for stores that block plain requests."""

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self._config = config or HttpClientConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._cloudflare_cleared = False
        self._uses_persistent_context = False
        self._uses_cdp = False
        self._challenge_visible_since: float | None = None

    def get_text(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
        accept_json: bool = False,
    ) -> str:
        del accept_json
        return self._fetch(url, params=params, referer=referer)

    def get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
    ) -> Any:
        import json

        return json.loads(self._fetch(url, params=params, referer=referer))

    def post_json(self, url: str, payload: dict[str, Any]) -> Any:
        import json

        self._ensure_page()
        response = self._page.request.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self._config.timeout_seconds * 1000,
        )

        if not response.ok:
            _raise_http_error(response.status, url)

        return response.json()

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        self._ensure_page()

        warmup_url = self._config.cloudflare_warmup_url or referer
        if warmup_url is not None and not self._cloudflare_cleared:
            self.ensure_cloudflare_cleared(warmup_url)

        if self._config.cloudflare_warmup_url is not None:
            if self._should_use_ui_post():
                return self.post_deck_builder_via_ui(url, data, referer=referer)
            return self._post_form_in_page(url, data, referer=referer)

        headers = {
            "Accept": "text/plain, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        if referer is not None:
            headers["Referer"] = referer

        response = self._page.request.post(
            url,
            form=data,
            headers=headers,
            timeout=self._config.timeout_seconds * 1000,
        )

        if not response.ok:
            _raise_http_error(response.status, url)

        return response.text()

    def ensure_cloudflare_cleared(self, warmup_url: str | None = None) -> None:
        if self._cloudflare_cleared:
            return

        target_url = warmup_url or self._config.cloudflare_warmup_url
        if target_url is None:
            self._cloudflare_cleared = True
            return

        self._ensure_page()

        if self._config.browser_cdp_url is not None:
            self._ensure_cdp_cloudflare_cleared()
            return

        if self._can_skip_cloudflare_wait():
            print("Skipping Cloudflare wait (#send2 and deck input visible).")
            self._cloudflare_cleared = True
            return

        if self._config.browser_manual_cf and (
            not self._config.browser_headless or self._config.browser_cdp_url is not None
        ):
            print(f"Attached browser tab: {self._page.url}")
            print(
                "When the Imaginaire deck builder is ready in that tab, "
                "press Enter IN THIS TERMINAL..."
            )
            input()
            self._cloudflare_cleared = True
            return

        timeout_seconds = (
            _HEADED_CF_TIMEOUT_SECONDS
            if (not self._config.browser_headless or self._config.browser_cdp_url)
            else _HEADLESS_CF_TIMEOUT_SECONDS
        )
        navigation_timeout_ms = timeout_seconds * 1000

        if not self._config.browser_headless or self._config.browser_cdp_url:
            print("Solve Cloudflare in the browser window; waiting...")

        if not self._is_on_deck_builder_page():
            self._page.goto(
                target_url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout_ms,
            )

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._invalidate_stale_cloudflare_cookies_if_needed()

            if self._is_cloudflare_challenge_cleared():
                self._cloudflare_cleared = True
                if not self._config.browser_headless:
                    print("Cloudflare cleared; ready for deck builder POST.")
                return

            if not self._config.browser_headless or self._config.browser_cdp_url:
                print(f"  {self._cloudflare_status_message()}")

            time.sleep(2)

        raise RuntimeError(
            "Cloudflare challenge did not clear in time. "
            "Try --browser-headed --browser-manual-cf or --browser-cdp-url."
        )

    def _ensure_cdp_cloudflare_cleared(self) -> None:
        if is_deck_builder_interactive_ready(self._page):
            print("Skipping Cloudflare wait (#send2 and deck input visible).")
            self._cloudflare_cleared = True
            return

        print(f"Attached browser tab: {self._page.url}")
        print(
            "When the Imaginaire deck builder is ready in that tab, press Enter IN THIS TERMINAL..."
        )
        input()
        self._cloudflare_cleared = True

    def post_deck_builder_via_ui(
        self,
        ajax_url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        from mtg_price_checker.infra.imaginaire_ui import (
            CloudflareBlockedResponseError,
            post_deck_builder_via_ui,
        )

        self._ensure_page()

        warmup_url = self._config.cloudflare_warmup_url or referer
        if warmup_url is not None and not self._cloudflare_cleared:
            self.ensure_cloudflare_cleared(warmup_url)

        deck_items_api = data.get("deckItems", "")
        condition = data.get("condition", "NM")

        def navigate(url: str) -> None:
            self._page.goto(url, wait_until="domcontentloaded")

        try:
            return post_deck_builder_via_ui(
                self._page,
                deck_items_api=deck_items_api,
                condition=condition,
                ajax_url=ajax_url,
                warmup_url=warmup_url,
                human_delays=self._config.browser_human_delays,
                is_on_deck_builder=self._is_on_deck_builder_page(),
                navigate=navigate,
                prefer_dom_capture=self._uses_cdp,
            )
        except CloudflareBlockedResponseError:
            if self._config.browser_cdp_url is None and self._config.browser_headless:
                raise
            print(
                "Cloudflare blocked the deck builder response. "
                "Solve the challenge in the browser, then press Enter IN THIS TERMINAL to retry..."
            )
            input()
            if warmup_url and not self._is_on_deck_builder_page():
                navigate(warmup_url)
            return post_deck_builder_via_ui(
                self._page,
                deck_items_api=deck_items_api,
                condition=condition,
                ajax_url=ajax_url,
                warmup_url=None,
                human_delays=self._config.browser_human_delays,
                is_on_deck_builder=self._is_on_deck_builder_page(),
                navigate=navigate,
                prefer_dom_capture=self._uses_cdp,
            )

    def get_context_cookies(self) -> list[dict[str, Any]]:
        self._ensure_page()
        return self._context.cookies()

    def can_skip_cloudflare_wait(self) -> bool:
        self._ensure_page()
        if self._config.browser_cdp_url is not None or (
            self._should_use_ui_post() and not self._config.browser_headless
        ):
            return self._is_deck_builder_session_ready()
        return False

    def _can_skip_cloudflare_wait(self) -> bool:
        return self.can_skip_cloudflare_wait()

    def _invalidate_stale_cloudflare_cookies_if_needed(self) -> None:
        if self._uses_cdp:
            return

        cookies = self._context.cookies()
        has_clearance = has_cf_clearance_cookie(cookies)
        challenge_visible = is_cloudflare_challenge_visible(self._page)

        if not challenge_visible:
            self._challenge_visible_since = None

        if not has_clearance or not challenge_visible:
            return

        if self._uses_cdp or self._config.browser_manual_cf:
            now = time.monotonic()
            if self._challenge_visible_since is None:
                self._challenge_visible_since = now
                return
            if now - self._challenge_visible_since < 5.0:
                return

        self._clear_cloudflare_cookies()
        self._challenge_visible_since = None
        if not self._config.browser_headless:
            print("  status: stale cf_clearance cleared, re-solve needed")
        if self._uses_cdp or self._config.browser_manual_cf:
            return
        self._page.reload(wait_until="domcontentloaded")

    def _clear_cloudflare_cookies(self) -> None:
        remaining = [
            cookie
            for cookie in self._context.cookies()
            if cookie.get("name") not in _CLOUDFLARE_COOKIE_NAMES
        ]
        self._context.clear_cookies()
        if remaining:
            self._context.add_cookies(remaining)

    def _cloudflare_status_message(self) -> str:
        cookies = self._context.cookies()
        has_clearance = has_cf_clearance_cookie(cookies)
        challenge_visible = is_cloudflare_challenge_visible(self._page)
        deck_builder_ready = is_deck_builder_ready(self._page)

        if challenge_visible and has_clearance:
            return "status: stale cf_clearance with challenge still visible"
        if challenge_visible:
            return "status: Cloudflare challenge visible"
        if has_clearance and not deck_builder_ready:
            return "status: cf_clearance present, waiting for deck builder"
        if not has_clearance:
            return "status: waiting for cf_clearance"
        return "status: waiting for deck builder"

    def _is_deck_builder_session_ready(self) -> bool:
        if not self._is_on_deck_builder_page():
            return False
        return is_deck_builder_interactive_ready(self._page)

    def _is_cloudflare_challenge_cleared(self) -> bool:
        if is_cloudflare_challenge_visible(self._page):
            return False

        cookies = self._context.cookies()
        if not has_cf_clearance_cookie(cookies):
            return False

        return self._is_on_deck_builder_page() or is_deck_builder_ready(self._page)

    def _is_on_deck_builder_page(self) -> bool:
        return _DECK_BUILDER_URL_FRAGMENT in self._page.url.lower()

    def _should_use_ui_post(self) -> bool:
        from mtg_price_checker.infra.imaginaire_ui import should_use_browser_ui_post

        return should_use_browser_ui_post(
            browser_ui_post=self._config.browser_ui_post,
            browser_cdp_url=self._config.browser_cdp_url,
            browser_only=self._config.browser_only,
            browser_headless=self._config.browser_headless,
        )

    def _post_form_in_page(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        result = self._page.evaluate(
            """
            async ({ url, data, referer }) => {
              const body = new URLSearchParams(data);
              const headers = {
                "Accept": "text/plain, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
              };
              if (referer) {
                headers["Referer"] = referer;
              }

              const response = await fetch(url, {
                method: "POST",
                headers,
                body,
                credentials: "include",
              });

              return {
                status: response.status,
                text: await response.text(),
              };
            }
            """,
            {"url": url, "data": data, "referer": referer},
        )

        status = result["status"]
        if status < 200 or status >= 300:
            _raise_http_error(status, url)

        return result["text"]

    def _fetch(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params)}"

        self._ensure_page()

        if referer is not None:
            self._page.set_extra_http_headers({"Referer": referer})

        response = self._page.request.get(url, timeout=self._config.timeout_seconds * 1000)

        if not response.ok:
            _raise_http_error(response.status, url)

        return response.text()

    def _ensure_page(self) -> None:
        if self._page is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for browser-backed store requests. "
                "Install with: pip install mtg-price-checker[browser]"
            ) from exc

        self._playwright = sync_playwright().start()

        if self._config.browser_cdp_url is not None:
            self._connect_over_cdp(self._config.browser_cdp_url)
            return

        launch_kwargs = _build_launch_kwargs(self._config)

        if self._should_use_persistent_context():
            profile_dir = self._config.browser_profile_dir
            if profile_dir is None:
                raise RuntimeError(
                    "browser_profile_dir is required for persistent browser context."
                )

            profile_dir.mkdir(parents=True, exist_ok=True)
            self._context = self._launch_persistent_context(
                sync_playwright=self._playwright,
                profile_dir=profile_dir,
                launch_kwargs=launch_kwargs,
            )
            self._uses_persistent_context = True
            if not self._uses_cdp:
                self._load_cookies_into_context()
        else:
            self._browser = self._launch_browser(
                sync_playwright=self._playwright,
                launch_kwargs=launch_kwargs,
            )
            self._context = self._browser.new_context(
                user_agent=self._config.user_agent,
                locale="fr-CA",
                timezone_id="America/Toronto",
            )
            self._load_cookies_into_context()

        pages = self._context.pages
        self._page = pages[0] if pages else self._context.new_page()

    def _connect_over_cdp(self, cdp_url: str) -> None:
        browser = self._playwright.chromium.connect_over_cdp(cdp_url)
        self._browser = browser
        self._uses_cdp = True

        if browser.contexts:
            self._context = browser.contexts[0]
        else:
            self._context = browser.new_context()

        self._page = _pick_deck_builder_page(self._context)
        print(f"CDP attached to: {self._page.url}")

    def _should_use_persistent_context(self) -> bool:
        if self._config.browser_cdp_url is not None:
            return False
        return (
            self._config.cloudflare_warmup_url is not None
            and self._config.browser_profile_dir is not None
        )

    def _launch_browser(self, *, sync_playwright: Any, launch_kwargs: dict[str, Any]) -> Any:
        chromium = sync_playwright.chromium
        try:
            return chromium.launch(channel="chrome", **launch_kwargs)
        except Exception:
            return chromium.launch(**launch_kwargs)

    def _launch_persistent_context(
        self,
        *,
        sync_playwright: Any,
        profile_dir: Path,
        launch_kwargs: dict[str, Any],
    ) -> Any:
        chromium = sync_playwright.chromium
        context_kwargs = {
            **launch_kwargs,
            "user_agent": self._config.user_agent,
            "locale": "fr-CA",
            "timezone_id": "America/Toronto",
        }
        try:
            return chromium.launch_persistent_context(
                str(profile_dir),
                channel="chrome",
                **context_kwargs,
            )
        except Exception:
            return chromium.launch_persistent_context(
                str(profile_dir),
                **context_kwargs,
            )

    def _load_cookies_into_context(self) -> None:
        if self._uses_cdp:
            return

        cookies_file = self._config.cookies_file
        if cookies_file is None or not cookies_file.exists():
            return

        playwright_cookies, skipped = playwright_cookies_from_file(cookies_file)
        if skipped:
            print(
                f"Skipped {skipped} Cloudflare cookie(s) from {cookies_file} "
                "(browser must earn its own cf_clearance)."
            )

        if playwright_cookies:
            self._context.add_cookies(playwright_cookies)

    def close(self) -> None:
        if self._uses_cdp:
            if self._playwright is not None:
                self._playwright.stop()
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._cloudflare_cleared = False
            self._uses_cdp = False
            return

        if self._context is not None:
            self._context.close()
        if self._browser is not None and not self._uses_persistent_context:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._cloudflare_cleared = False
        self._uses_persistent_context = False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def is_cloudflare_challenge_visible_in_html(content: str) -> bool:
    if _CLOUDFLARE_CHALLENGE_TEXT in content:
        return True
    return any(pattern.search(content) for pattern in _CLOUDFLARE_VERIFY_PATTERNS)


def has_cf_clearance_cookie(cookies: list[dict[str, Any]]) -> bool:
    return any(cookie.get("name") == "cf_clearance" for cookie in cookies)


def is_deck_builder_ready_in_html(content: str) -> bool:
    lowered = content.lower()
    if "textarea" in lowered:
        return True
    if 'name="deckitems"' in lowered or 'id="deckitems"' in lowered:
        return True
    return "constructeur" in lowered and "deck" in lowered


def is_successful_deck_builder_response(html: str) -> bool:
    lowered = html.lower()
    return "card-listing" in lowered or "magictitle" in lowered


def is_cloudflare_challenge_visible(page: Any) -> bool:
    if is_deck_builder_interactive_ready(page):
        return False

    content = page.content()
    if is_cloudflare_challenge_visible_in_html(content):
        return True

    try:
        if _locator_is_visible(page, 'iframe[src*="challenges.cloudflare"]'):
            return True
        if _locator_is_visible(page, "#cf-turnstile"):
            return True
        if _locator_is_visible(page, ".cf-turnstile"):
            return True
    except Exception:
        return False

    return False


def is_deck_builder_interactive_ready(page: Any) -> bool:
    try:
        has_input = False
        for selector in ("textarea", 'input[name="deckItems"]', "#deckItems"):
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible():
                has_input = True
                break

        submit = page.locator("#send2").first
        has_submit = submit.count() > 0 and submit.is_visible()
        return has_input and has_submit
    except Exception:
        return False


def _locator_is_visible(page: Any, selector: str) -> bool:
    try:
        locator = page.locator(selector).first
        return locator.count() > 0 and locator.is_visible()
    except Exception:
        return False


def is_deck_builder_ready(page: Any) -> bool:
    if is_deck_builder_ready_in_html(page.content()):
        return True

    try:
        if page.locator("textarea").count() > 0:
            return True
        if page.locator('input[name="deckItems"], #deckItems').count() > 0:
            return True
        if page.locator("#send2").count() > 0:
            return True
    except Exception:
        return False

    return False


def _pick_deck_builder_page(context: Any) -> Any:
    for page in context.pages:
        if _DECK_BUILDER_URL_FRAGMENT in page.url.lower():
            return page
    pages = context.pages
    return pages[0] if pages else context.new_page()


def playwright_cookies_from_file(
    cookies_file: Path,
    *,
    base_url: str = _COOKIE_BASE_URL,
) -> tuple[list[dict[str, Any]], int]:
    cookie_jar = MozillaCookieJar(str(cookies_file))
    cookie_jar.load(ignore_discard=True, ignore_expires=True)

    playwright_cookies: list[dict[str, Any]] = []
    skipped = 0

    for cookie in cookie_jar:
        if should_skip_browser_cookie(cookie):
            skipped += 1
            continue
        playwright_cookies.append(cookie_to_playwright_entry(cookie, base_url=base_url))

    return playwright_cookies, skipped


def should_skip_browser_cookie(cookie: Cookie) -> bool:
    return cookie.name in _SKIP_BROWSER_COOKIE_NAMES


def cookie_to_playwright_entry(cookie: Cookie, *, base_url: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": cookie.name,
        "value": cookie.value,
        "url": base_url,
    }
    if cookie.expires:
        entry["expires"] = int(cookie.expires)
    if cookie.secure:
        entry["secure"] = True
    return entry


def _build_launch_kwargs(config: HttpClientConfig) -> dict[str, Any]:
    return {
        "headless": config.browser_headless,
        "args": list(_STEALTH_LAUNCH_ARGS),
        "ignore_default_args": list(_STEALTH_IGNORE_DEFAULT_ARGS),
    }


def _raise_http_error(status_code: int, url: str) -> None:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    raise requests.HTTPError(f"{status_code} Client Error for url: {url}", response=response)
