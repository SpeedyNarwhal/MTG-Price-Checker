import re
from decimal import Decimal
from typing import Any

import requests
from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import StoreAdapter
from mtg_price_checker.stores.shopify_common import (
    parse_shopify_condition_variants,
    search_product_urls,
    to_shopify_product_json_url,
)

_SILVER_GOBLIN_BASE_URL = "https://silvergoblin.cards"

_SET_AND_COLLECTOR_PATTERN = re.compile(r"\((?P<collector_number>[A-Z0-9]+)\)")


class SilverGoblinStoreAdapter(StoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 12,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check
        self._last_listings_checked = 0

    @property
    def store_id(self) -> str:
        return "silvergoblin"

    @property
    def display_name(self) -> str:
        return "Silver Goblin"

    @property
    def last_listings_checked(self) -> int:
        return self._last_listings_checked

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        product_urls = search_product_urls(
            self._http_client,
            _SILVER_GOBLIN_BASE_URL,
            requested_card.normalized_name,
        )
        product_urls_to_check = product_urls[: self._max_products_to_check]
        self._last_listings_checked = len(product_urls_to_check)
        quotes: list[StoreQuote] = []

        for product_url in product_urls_to_check:
            product_json_url = to_shopify_product_json_url(product_url, _SILVER_GOBLIN_BASE_URL)

            try:
                product_json = self._http_client.get_json(
                    product_json_url,
                    referer=f"{_SILVER_GOBLIN_BASE_URL}/",
                )
                quotes.extend(
                    parse_silver_goblin_product_json(
                        product_json=product_json,
                        product_url=product_url,
                        requested_card=requested_card,
                    )
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {403, 429}:
                    raise

                product_html = self._http_client.get_text(
                    product_url,
                    referer=f"{_SILVER_GOBLIN_BASE_URL}/",
                )
                quotes.extend(
                    parse_silver_goblin_product_page_html(
                        html=product_html,
                        product_url=product_url,
                        requested_card=requested_card,
                    )
                )
            except Exception:
                product_html = self._http_client.get_text(
                    product_url,
                    referer=f"{_SILVER_GOBLIN_BASE_URL}/",
                )
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
    return parse_shopify_condition_variants(
        product_json,
        product_url,
        requested_card,
        store_id="silvergoblin",
        extract_card_name_from_title=_extract_card_name_from_title,
        extract_collector_number=_extract_collector_number,
        default_finish_from_title=_extract_finish,
    )


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


def _extract_finish(value: str) -> Finish:
    normalized = value.lower()

    if re.search(r"\bnon[-\s]?foil\b", normalized):
        return Finish.NONFOIL

    if re.search(r"\bfoil\b", normalized):
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_regular_price(page_text: str) -> Decimal | None:
    match = re.search(r"Regular price\s+\$(?P<price>\d+(?:\.\d{2})?)\s+CAD", page_text)

    if match is None:
        return None

    return Decimal(match.group("price"))


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
