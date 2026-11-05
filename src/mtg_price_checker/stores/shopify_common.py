import re
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient

_SUGGEST_MAX_PRODUCTS = 10

_CONDITION_LABELS = {
    "Near Mint": CardCondition.NEAR_MINT,
    "Lightly Played": CardCondition.LIGHTLY_PLAYED,
    "Moderately Played": CardCondition.MODERATELY_PLAYED,
    "Heavily Played": CardCondition.HEAVILY_PLAYED,
    "Damaged": CardCondition.DAMAGED,
    "NM": CardCondition.NEAR_MINT,
    "LP": CardCondition.LIGHTLY_PLAYED,
    "MP": CardCondition.MODERATELY_PLAYED,
    "HP": CardCondition.HEAVILY_PLAYED,
    "DMG": CardCondition.DAMAGED,
}


def search_product_urls(
    http_client: HttpClient,
    base_url: str,
    query: str,
) -> list[str]:
    suggest_urls = _fetch_suggest_product_urls(http_client, base_url, query)
    html_urls = _fetch_html_search_product_urls(http_client, base_url, query)
    return merge_product_urls(suggest_urls, html_urls)


def merge_product_urls(*url_lists: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for urls in url_lists:
        for url in urls:
            if url in seen:
                continue

            seen.add(url)
            merged.append(url)

    return merged


def _fetch_suggest_product_urls(
    http_client: HttpClient,
    base_url: str,
    query: str,
) -> list[str]:
    try:
        suggest_json = http_client.get_json(
            f"{base_url}/search/suggest.json",
            params={
                "q": query,
                "resources[type]": "product",
                "resources[limit]": str(_SUGGEST_MAX_PRODUCTS),
                "resources[limit_scope]": "each",
            },
            referer=f"{base_url}/",
        )
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {403, 429}:
            raise

        return []

    return extract_product_urls_from_suggest_json(suggest_json, base_url)


def _fetch_html_search_product_urls(
    http_client: HttpClient,
    base_url: str,
    query: str,
) -> list[str]:
    search_html = http_client.get_text(
        f"{base_url}/search",
        params={
            "q": query,
            "type": "product",
        },
        referer=f"{base_url}/",
    )

    return extract_product_urls_from_search_html(search_html, base_url)


def extract_product_urls_from_suggest_json(payload: Any, base_url: str) -> list[str]:
    urls: list[str] = []

    if not isinstance(payload, dict):
        return urls

    resources = payload.get("resources")

    if not isinstance(resources, dict):
        return urls

    results = resources.get("results")

    if not isinstance(results, dict):
        return urls

    products = results.get("products")

    if not isinstance(products, list):
        return urls

    for product in products:
        if not isinstance(product, dict):
            continue

        raw_url = product.get("url")

        if not isinstance(raw_url, str):
            continue

        absolute_url = urljoin(base_url, raw_url).split("?")[0]

        if "/products/" not in absolute_url:
            continue

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def extract_product_urls_from_search_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href_value = link.get("href")

        if not isinstance(href_value, str):
            continue

        if "/products/" not in href_value:
            continue

        absolute_url = urljoin(base_url, href_value).split("?")[0]

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def to_shopify_product_json_url(product_url: str, base_url: str) -> str:
    parsed = urlparse(product_url)
    path = parsed.path.rstrip("/")

    if path.endswith(".js"):
        return product_url

    return f"{base_url}{path}.js"


def parse_shopify_condition_variants(
    product_json: dict[str, Any],
    product_url: str,
    requested_card: RequestedCard,
    store_id: str,
    *,
    extract_card_name_from_title: Any,
    extract_collector_number: Any | None = None,
    extract_set_code: Any | None = None,
    default_finish_from_title: Any | None = None,
) -> list[StoreQuote]:
    title = _safe_string(product_json.get("title"))

    if title is None:
        return []

    matched_card_name = extract_card_name_from_title(title)

    if not card_names_match(requested_card.normalized_name, matched_card_name):
        return []

    collector_number = extract_collector_number(title) if extract_collector_number else None
    set_code = extract_set_code(title) if extract_set_code else None
    default_finish = (
        default_finish_from_title(title) if default_finish_from_title else Finish.NONFOIL
    )
    variants = product_json.get("variants")

    if not isinstance(variants, list):
        return []

    quotes: list[StoreQuote] = []

    for variant in variants:
        if not isinstance(variant, dict):
            continue

        variant_title = _safe_string(variant.get("title")) or ""
        condition = _extract_condition(variant_title)

        if condition is None:
            continue

        finish = _extract_finish(variant_title)
        if finish == Finish.NONFOIL:
            finish = default_finish

        available = bool(variant.get("available"))
        price = _extract_price_from_variant(variant)

        quotes.append(
            StoreQuote(
                store_id=store_id,
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=available and price is not None,
                product_url=product_url,
                set_code=set_code,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=1.0,
            )
        )

    if quotes:
        return quotes

    for variant in variants:
        if not isinstance(variant, dict):
            continue

        available = bool(variant.get("available"))
        price = _extract_price_from_variant(variant)

        quotes.append(
            StoreQuote(
                store_id=store_id,
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=CardCondition.NEAR_MINT,
                finish=default_finish,
                price_cad=price,
                in_stock=available and price is not None,
                product_url=product_url,
                set_code=set_code,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=0.8,
            )
        )

    return quotes


def _extract_condition(value: str) -> CardCondition | None:
    normalized_value = _simple_normalize(value)

    for label, condition in _CONDITION_LABELS.items():
        if _simple_normalize(label) in normalized_value:
            return condition

    return None


def _extract_finish(value: str) -> Finish:
    normalized = value.lower()

    if re.search(r"\bnon[-\s]?foil\b", normalized):
        return Finish.NONFOIL

    if re.search(r"\bfoil\b", normalized):
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_price_from_variant(variant: dict[str, Any]) -> Decimal | None:
    raw_price = variant.get("price")

    if isinstance(raw_price, int):
        return Decimal(raw_price) / Decimal("100")

    if isinstance(raw_price, float):
        return Decimal(str(raw_price))

    if isinstance(raw_price, str):
        cleaned = raw_price.replace("$", "").replace("CAD", "").strip()

        try:
            value = Decimal(cleaned)
        except Exception:
            return None

        if value >= Decimal("100"):
            return value / Decimal("100")

        return value

    return None


def card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _safe_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None
