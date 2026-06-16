from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from mtg_price_checker.infra.http_client import HttpClient, HttpClientConfig

DEFAULT_CARDS = ["Sol Ring", "Arcane Signet", "Counterspell"]

STORES = {
    "danireon": "https://www.danireon.com",
    "silvergoblin": "https://silvergoblin.cards",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class ProbeResult:
    strategy: str
    store: str
    card: str
    step: str
    status_code: int | str
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe store HTTP behavior under run-like patterns."
    )
    parser.add_argument(
        "--cards",
        nargs="+",
        default=DEFAULT_CARDS,
        help="Card names to probe in sequence.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay between steps when using the app HttpClient.",
    )
    args = parser.parse_args()

    print("=== Single-request baseline (requests library) ===")
    for store_name, base_url in STORES.items():
        for card in args.cards[:1]:
            _print_probe(
                _probe_single_request(
                    store=store_name,
                    base_url=base_url,
                    card=card,
                )
            )

    print("\n=== Cold session mini-run (new Session per card) ===")
    for store_name, base_url in STORES.items():
        for card in args.cards:
            for probe in _probe_card_flow(
                strategy="cold-session",
                store=store_name,
                base_url=base_url,
                card=card,
                session_factory=lambda: requests.Session(),
                delay_seconds=0.0,
            ):
                _print_probe(probe)

    print("\n=== Warmed session mini-run (shared Session + homepage) ===")
    for store_name, base_url in STORES.items():
        session = requests.Session()
        session.headers.update(BROWSER_HEADERS)
        session.get(base_url, timeout=20)

        for card in args.cards:
            for probe in _probe_card_flow(
                strategy="warmed-session",
                store=store_name,
                base_url=base_url,
                card=card,
                session_factory=lambda: session,
                delay_seconds=0.0,
            ):
                _print_probe(probe)

    print("\n=== App HttpClient mini-run (warmup + suggest.json + product.js) ===")
    for store_name, base_url in STORES.items():
        http_client = HttpClient(
            HttpClientConfig(
                min_seconds_between_requests=args.delay_seconds,
                use_cache=False,
            )
        )

        for card in args.cards:
            for probe in _probe_with_http_client(
                strategy="app-http-client",
                store=store_name,
                base_url=base_url,
                card=card,
                http_client=http_client,
            ):
                _print_probe(probe)


def _probe_single_request(store: str, base_url: str, card: str) -> ProbeResult:
    query = urlencode(
        {
            "q": card,
            "resources[type]": "product",
            "resources[limit]": "3",
        }
    )
    url = f"{base_url}/search/suggest.json?{query}"

    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        status_code = response.status_code
        detail = _collapse_whitespace(response.text)[:120]
    except requests.RequestException as exc:
        status_code = "REQUEST_ERROR"
        detail = str(exc)

    return ProbeResult(
        strategy="single-request",
        store=store,
        card=card,
        step="suggest.json",
        status_code=status_code,
        detail=detail,
    )


def _probe_card_flow(
    strategy: str,
    store: str,
    base_url: str,
    card: str,
    session_factory,
    delay_seconds: float,
) -> list[ProbeResult]:
    session = session_factory()
    session.headers.update(BROWSER_HEADERS)
    results: list[ProbeResult] = []

    suggest_url = (
        f"{base_url}/search/suggest.json?"
        f"{urlencode({'q': card, 'resources[type]': 'product', 'resources[limit]': '3'})}"
    )

    try:
        suggest_response = session.get(suggest_url, timeout=20)
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="suggest.json",
                status_code=suggest_response.status_code,
                detail=_collapse_whitespace(suggest_response.text)[:120],
            )
        )
        product_url = _first_product_url(suggest_response.json(), base_url)
    except requests.RequestException as exc:
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="suggest.json",
                status_code="REQUEST_ERROR",
                detail=str(exc),
            )
        )
        return results

    if product_url is None:
        return results

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    product_js_url = f"{product_url}.js" if not product_url.endswith(".js") else product_url

    try:
        product_response = session.get(
            product_js_url,
            headers={**BROWSER_HEADERS, "Referer": f"{base_url}/"},
            timeout=20,
        )
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="product.js",
                status_code=product_response.status_code,
                detail=_collapse_whitespace(product_response.text)[:120],
            )
        )
    except requests.RequestException as exc:
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="product.js",
                status_code="REQUEST_ERROR",
                detail=str(exc),
            )
        )

    return results


def _probe_with_http_client(
    strategy: str,
    store: str,
    base_url: str,
    card: str,
    http_client: HttpClient,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    try:
        suggest_json = http_client.get_json(
            f"{base_url}/search/suggest.json",
            params={
                "q": card,
                "resources[type]": "product",
                "resources[limit]": "3",
            },
            referer=f"{base_url}/",
        )
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="suggest.json",
                status_code=200,
                detail=_collapse_whitespace(str(suggest_json))[:120],
            )
        )
        product_url = _first_product_url(suggest_json, base_url)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "HTTP_ERROR"
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="suggest.json",
                status_code=status_code,
                detail=str(exc),
            )
        )
        return results

    if product_url is None:
        return results

    product_js_url = f"{product_url}.js" if not product_url.endswith(".js") else product_url

    try:
        product_json = http_client.get_json(product_js_url, referer=f"{base_url}/")
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="product.js",
                status_code=200,
                detail=_collapse_whitespace(str(product_json))[:120],
            )
        )
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "HTTP_ERROR"
        results.append(
            ProbeResult(
                strategy=strategy,
                store=store,
                card=card,
                step="product.js",
                status_code=status_code,
                detail=str(exc),
            )
        )

    return results


def _first_product_url(payload: object, base_url: str) -> str | None:
    if not isinstance(payload, dict):
        return None

    resources = payload.get("resources")
    if not isinstance(resources, dict):
        return None

    results = resources.get("results")
    if not isinstance(results, dict):
        return None

    products = results.get("products")
    if not isinstance(products, list):
        return None

    for product in products:
        if not isinstance(product, dict):
            continue

        raw_url = product.get("url")
        if isinstance(raw_url, str) and "/products/" in raw_url:
            return f"{base_url}{raw_url}".split("?")[0]

    return None


def _print_probe(probe: ProbeResult) -> None:
    print(f"strategy: {probe.strategy}")
    print(f"store: {probe.store}")
    print(f"card: {probe.card}")
    print(f"step: {probe.step}")
    print(f"status: {probe.status_code}")
    print(f"detail: {probe.detail}")
    print()


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    main()
