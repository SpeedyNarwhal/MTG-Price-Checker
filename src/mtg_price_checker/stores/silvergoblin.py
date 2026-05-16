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
from mtg_price_checker.stores.base import StoreAdapter

_SILVER_GOBLIN_BASE_URL = "https://silvergoblin.cards"

_CONDITION_LABELS = {
    "Near Mint": CardCondition.NEAR_MINT,
    "Lightly Played": CardCondition.LIGHTLY_PLAYED,
    "Moderately Played": CardCondition.MODERATELY_PLAYED,
    "Heavily Played": CardCondition.HEAVILY_PLAYED,
    "Damaged": CardCondition.DAMAGED,
}

_SET_AND_COLLECTOR_PATTERN = re.compile(r"\((?P<collector_number>[A-Z0-9]+)\)")


class SilverGoblinStoreAdapter(StoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 5,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check

    @property
    def store_id(self) -> str:
        return "silvergoblin"

    @property
    def display_name(self) -> str:
        return "Silver Goblin"

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        search_html = self._http_client.get_text(
            f"{_SILVER_GOBLIN_BASE_URL}/search",
            params={
                "q": requested_card.normalized_name,
                "type": "product",
            },
        )

        product_urls = _extract_product_urls(search_html)
        quotes: list[StoreQuote] = []

        for product_url in product_urls[: self._max_products_to_check]:
            product_json_url = _to_shopify_product_json_url(product_url)

            try:
                product_json = self._http_client.get_json(product_json_url)
                quotes.extend(
                    parse_silver_goblin_product_json(
                        product_json=product_json,
                        product_url=product_url,
                        requested_card=requested_card,
                    )
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    raise

                product_html = self._http_client.get_text(product_url)
                quotes.extend(
                    parse_silver_goblin_product_page_html(
                        html=product_html,
                        product_url=product_url,
                        requested_card=requested_card,
                    )
                )
            except Exception:
                product_html = self._http_client.get_text(product_url)
                quotes.extend(
                    parse_silver_goblin_product_page_html(
                        html=product_html,
                        product_url=product_url,
                        requested_card=requested_card,
                    )
                )

        return quotes


def parse_silver_goblin_product_json(
    product_json: dict[str, Any],
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    title = _safe_string(product_json.get("title"))

    if title is None:
        return []

    matched_card_name = _extract_card_name_from_title(title)

    if not _card_names_match(requested_card.normalized_name, matched_card_name):
        return []

    collector_number = _extract_collector_number(title)
    default_finish = _extract_finish(title)
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
                store_id="silvergoblin",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=available and price is not None,
                product_url=product_url,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=1.0,
            )
        )

    if quotes:
        return quotes

    # Some Silver Goblin singles appear to use a single/default Shopify variant
    # instead of condition-labelled variants. For those, treat the product as NM.
    for variant in variants:
        if not isinstance(variant, dict):
            continue

        available = bool(variant.get("available"))
        price = _extract_price_from_variant(variant)

        quotes.append(
            StoreQuote(
                store_id="silvergoblin",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=CardCondition.NEAR_MINT,
                finish=default_finish,
                price_cad=price,
                in_stock=available and price is not None,
                product_url=product_url,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=0.8,
            )
        )

    return quotes


def parse_silver_goblin_product_page_html(
    html: str,
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)

    if title is None:
        return []

    matched_card_name = _extract_card_name_from_title(title)

    if not _card_names_match(requested_card.normalized_name, matched_card_name):
        return []

    page_text = soup.get_text(" ", strip=True)
    price = _extract_regular_price(page_text)
    finish = _extract_finish(title)
    collector_number = _extract_collector_number(title)

    # Conservative fallback:
    # If the page explicitly says Near Mint is sold out/unavailable, mark it out of stock.
    # Otherwise, only mark as in stock if the page has Add to cart and some stock text.
    near_mint_unavailable = re.search(
        r"Near Mint\s+Variant sold out or unavailable",
        page_text,
        re.IGNORECASE,
    )
    appears_available = "Add to cart" in page_text and "in stock" in page_text

    in_stock = near_mint_unavailable is None and appears_available and price is not None

    return [
        StoreQuote(
            store_id="silvergoblin",
            requested_card_name=requested_card.normalized_name,
            matched_card_name=matched_card_name,
            condition=CardCondition.NEAR_MINT,
            finish=finish,
            price_cad=price,
            in_stock=in_stock,
            product_url=product_url,
            collector_number=collector_number,
            raw_title=title,
            confidence_score=0.7,
        )
    ]


def _extract_product_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href_value = link.get("href")

        if not isinstance(href_value, str):
            continue

        if "/products/" not in href_value:
            continue

        absolute_url = urljoin(_SILVER_GOBLIN_BASE_URL, href_value).split("?")[0]

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def _to_shopify_product_json_url(product_url: str) -> str:
    parsed = urlparse(product_url)
    path = parsed.path.rstrip("/")

    if path.endswith(".js"):
        return product_url

    return f"{_SILVER_GOBLIN_BASE_URL}{path}.js"


def _extract_title(soup: BeautifulSoup) -> str | None:
    for selector in ["h1", "h2"]:
        heading = soup.find(selector)

        if heading is None:
            continue

        title = heading.get_text(" ", strip=True)

        if title:
            return title

    meta_title = soup.find("meta", property="og:title")

    if meta_title is not None:
        content = meta_title.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

    return None


def _extract_card_name_from_title(title: str) -> str:
    before_collector_number = title.split("(", maxsplit=1)[0]
    return before_collector_number.strip()


def _extract_collector_number(title: str) -> str | None:
    match = _SET_AND_COLLECTOR_PATTERN.search(title)

    if match is None:
        return None

    return match.group("collector_number")


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

        # Shopify product JSON often gives cents as a numeric string.
        if value >= Decimal("100"):
            return value / Decimal("100")

        return value

    return None


def _extract_regular_price(page_text: str) -> Decimal | None:
    match = re.search(r"Regular price\s+\$(?P<price>\d+(?:\.\d{2})?)\s+CAD", page_text)

    if match is None:
        return None

    return Decimal(match.group("price"))


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _safe_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None
