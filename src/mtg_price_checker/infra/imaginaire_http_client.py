from __future__ import annotations

from dataclasses import replace

from mtg_price_checker.infra.browser_http_client import BrowserHttpClient
from mtg_price_checker.infra.http_client import HttpClientConfig
from mtg_price_checker.infra.imaginaire_ui import should_use_browser_ui_post
from mtg_price_checker.infra.impersonating_http_client import ImpersonatingHttpClient

_IMAGINAIRE_WARMUP_URL = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"


def _is_http_403(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) == 403:
        return True

    message = str(exc)
    return "403" in message


class ImaginaireHttpClient:
    """Tiered HTTP client for Imaginaire: TLS impersonation, then Playwright fallback."""

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        base_config = config or HttpClientConfig()
        if base_config.cloudflare_warmup_url is None:
            base_config = replace(
                base_config,
                cloudflare_warmup_url=_IMAGINAIRE_WARMUP_URL,
            )

        self._config = base_config
        self._browser = BrowserHttpClient(self._config)
        self._impersonating = (
            None
            if should_skip_tls(self._config)
            else _try_create_impersonating_client(self._config)
        )

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        if self._impersonating is not None and not self._should_use_ui_post():
            try:
                return self._impersonating.post_form(url, data, referer=referer)
            except Exception as exc:
                if not _is_http_403(exc):
                    raise

        if not self._can_skip_cloudflare_wait():
            warmup_url = self._config.cloudflare_warmup_url or referer
            if warmup_url is not None:
                self._browser.ensure_cloudflare_cleared(warmup_url)

        html = self._browser.post_form(url, data, referer=referer)

        if self._impersonating is not None:
            self._impersonating.sync_cookies_from_browser(self._browser)

        return html

    def close(self) -> None:
        self._browser.close()
        if self._impersonating is not None:
            self._impersonating.close()

    def _can_skip_cloudflare_wait(self) -> bool:
        return self._browser.can_skip_cloudflare_wait()

    def _should_use_ui_post(self) -> bool:
        return should_use_browser_ui_post(
            browser_ui_post=self._config.browser_ui_post,
            browser_cdp_url=self._config.browser_cdp_url,
            browser_only=self._config.browser_only,
            browser_headless=self._config.browser_headless,
        )


def should_skip_tls(config: HttpClientConfig) -> bool:
    return (
        not config.browser_headless
        or config.browser_only
        or config.browser_manual_cf
        or config.browser_cdp_url is not None
    )


def _try_create_impersonating_client(
    config: HttpClientConfig,
) -> ImpersonatingHttpClient | None:
    try:
        return ImpersonatingHttpClient(config)
    except RuntimeError:
        return None
