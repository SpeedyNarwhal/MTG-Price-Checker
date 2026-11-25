from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from mtg_price_checker.infra.browser_http_client import BrowserHttpClient
from mtg_price_checker.infra.http_client import HttpClientConfig

_IMAGINAIRE_WARMUP_URL = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"

StatusCallback = Callable[[str], None]


class ImaginaireHttpClient:
    """Playwright-backed HTTP client for Imaginaire (Cloudflare requires a real browser)."""

    def __init__(self, config: HttpClientConfig | None = None) -> None:
        base_config = config or HttpClientConfig()
        if base_config.cloudflare_warmup_url is None:
            base_config = replace(
                base_config,
                cloudflare_warmup_url=_IMAGINAIRE_WARMUP_URL,
            )

        self._config = base_config
        self._browser = BrowserHttpClient(self._config)

    def ensure_cloudflare_cleared(
        self,
        warmup_url: str | None = None,
        *,
        status_callback: StatusCallback | None = None,
    ) -> None:
        target = warmup_url or self._config.cloudflare_warmup_url
        self._browser.ensure_cloudflare_cleared(target, status_callback=status_callback)

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        if not self._browser.can_skip_cloudflare_wait():
            warmup_url = self._config.cloudflare_warmup_url or referer
            if warmup_url is not None:
                self._browser.ensure_cloudflare_cleared(warmup_url)

        return self._browser.post_form(url, data, referer=referer)

    def close(self) -> None:
        self._browser.close()
