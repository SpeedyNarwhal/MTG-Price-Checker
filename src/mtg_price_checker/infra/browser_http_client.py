from __future__ import annotations

from typing import Any

import requests

from mtg_price_checker.infra.http_client import HttpClientConfig


class BrowserHttpClient:
    """Playwright-backed HTTP client for stores that block plain requests."""

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self._config = config or HttpClientConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def get_text(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
        accept_json: bool = False,
    ) -> str:
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

    def _fetch(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        from urllib.parse import urlencode

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
                "Playwright is required for --use-browser. "
                "Install with: pip install mtg-price-checker[browser]"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(user_agent=self._config.user_agent)
        self._page = self._context.new_page()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _raise_http_error(status_code: int, url: str) -> None:
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    raise requests.HTTPError(f"{status_code} Client Error for url: {url}", response=response)
