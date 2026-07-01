from __future__ import annotations

from typing import Any

from mtg_price_checker.infra.http_client import HttpClientConfig

_IMPERSONATE_TARGET = "chrome"


class ImpersonatingHttpClient:
    """curl_cffi-backed HTTP client with Chrome TLS impersonation."""

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self._config = config or HttpClientConfig()

        try:
            from curl_cffi import requests as curl_requests
        except ImportError as exc:
            raise RuntimeError(
                "curl_cffi is required for TLS impersonation. "
                "Install with: pip install mtg-price-checker[cloudflare]"
            ) from exc

        self._curl_requests = curl_requests
        self._session = curl_requests.Session(impersonate=_IMPERSONATE_TARGET)
        self._session.headers.update(
            {
                "User-Agent": self._config.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self._load_cookies_file()

    def get_text(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        referer: str | None = None,
        accept_json: bool = False,
    ) -> str:
        headers = self._build_headers(referer=referer, accept_json=accept_json)
        response = self._session.get(
            url,
            params=params,
            headers=headers,
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        headers = self._build_headers(referer=referer, accept_json=False)
        headers["Accept"] = "text/plain, */*; q=0.01"
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        response = self._session.post(
            url,
            data=data,
            headers=headers,
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def sync_cookies_from_browser(self, browser_client: Any) -> None:
        if not hasattr(browser_client, "get_context_cookies"):
            return

        for cookie in browser_client.get_context_cookies():
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue

            self._session.cookies.set(
                name,
                value,
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )

    def close(self) -> None:
        self._session.close()

    def _build_headers(
        self,
        *,
        referer: str | None = None,
        accept_json: bool = False,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if accept_json:
            headers["Accept"] = "application/json, text/plain, */*"
        if referer is not None:
            headers["Referer"] = referer
        return headers

    def _load_cookies_file(self) -> None:
        cookies_file = self._config.cookies_file
        if cookies_file is None or not cookies_file.exists():
            return

        from http.cookiejar import MozillaCookieJar

        cookie_jar = MozillaCookieJar(str(cookies_file))
        cookie_jar.load(ignore_discard=True, ignore_expires=True)

        for cookie in cookie_jar:
            self._session.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain,
                path=cookie.path or "/",
            )
