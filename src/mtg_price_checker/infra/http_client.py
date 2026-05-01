import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests


@dataclass(frozen=True)
class HttpClientConfig:
    timeout_seconds: int = 20
    user_agent: str = "mtg-price-checker/0.1 personal-use price checker"
    min_seconds_between_requests: float = 3.0
    max_retries: int = 1
    retry_backoff_seconds: float = 10.0
    cache_dir: Path = Path(".cache/http")
    use_cache: bool = True


class HttpClient:
    def __init__(self, config: HttpClientConfig | None = None) -> None:
        self._config = config or HttpClientConfig()
        self._session = requests.Session()
        self._last_request_at = 0.0

        self._session.headers.update(
            {
                "User-Agent": self._config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        cache_path = self._get_cache_path(url, params)

        if self._config.use_cache and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        response_text = self._get_text_uncached(url, params)

        if self._config.use_cache:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(response_text, encoding="utf-8")

        return response_text

    def get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        response_text = self.get_text(url, params=params)
        return json.loads(response_text)

    def _get_text_uncached(self, url: str, params: dict[str, str] | None = None) -> str:
        last_error: requests.HTTPError | None = None

        for attempt in range(self._config.max_retries + 1):
            self._wait_for_rate_limit()

            response = self._session.get(
                url,
                params=params,
                timeout=self._config.timeout_seconds,
            )

            if response.status_code == 429 and attempt < self._config.max_retries:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                sleep_seconds = retry_after or self._config.retry_backoff_seconds
                time.sleep(sleep_seconds)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_error = exc
                break

            return response.text

        if last_error is not None:
            raise last_error

        raise RuntimeError(f"Failed to fetch URL: {url}")

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._config.min_seconds_between_requests - elapsed

        if remaining > 0:
            time.sleep(remaining)

        self._last_request_at = time.monotonic()

    def _get_cache_path(self, url: str, params: dict[str, str] | None) -> Path:
        query = urlencode(params or {})
        cache_key = hashlib.sha256(f"{url}?{query}".encode("utf-8")).hexdigest()
        return self._config.cache_dir / f"{cache_key}.html"


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except ValueError:
        return None
