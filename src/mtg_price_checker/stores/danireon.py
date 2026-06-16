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

_DANIREON_BASE_URL = "https://www.danireon.com"

_CONDITION_LABELS = {
    "Near Mint": CardCondition.NEAR_MINT,
    "Lightly Played": CardCondition.LIGHTLY_PLAYED,
    "Moderately Played": CardCondition.MODERATELY_PLAYED,
    "Heavily Played": CardCondition.HEAVILY_PLAYED,
    "Damaged": CardCondition.DAMAGED,
}

_CONDITION_PATTERN = re.compile(
    r"(?P<condition>Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged)"
    r"\s*-\s*"
    r"(?:(?P<sold_out_without_price>Sold out)|"
    r"\$(?P<price>\d+(?:\.\d{2})?)\s*CAD"
    r"(?P<sold_out_with_price>\s*-\s*sold out!?)?)",
    re.IGNORECASE,
)

_SET_AND_COLLECTOR_PATTERN = re.compile(
    r"\((?P<set_code>[A-Z0-9]{2,5})-(?P<collector_number>[A-Z0-9]+)\)"
)


class DanireonStoreAdapter(StoreAdapter):
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
        return "danireon"

    @property
    def display_name(self) -> str:
        return "Danireon"

    @property
    def last_listings_checked(self) -> int:
        return self._last_listings_checked

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        product_urls = search_product_urls(
            self._http_client,
            _DANIREON_BASE_URL,
            requested_card.normalized_name,
        )
        product_urls_to_check = product_urls[: self._max_products_to_check]
        self._last_listings_checked = len(product_urls_to_check)

        quotes: list[StoreQuote] = []

        for product_url in product_urls_to_check:
            quotes.extend(
                self._fetch_product_quotes(
                    product_url=product_url,
                    requested_card=requested_card,
                )
            )

        return quotes

    def _fetch_product_quotes(
        self,
        product_url: str,
        requested_card: RequestedCard,
    ) -> list[StoreQuote]:
        product_json_url = to_shopify_product_json_url(product_url, _DANIREON_BASE_URL)

        try:
            product_json = self._http_client.get_json(
                product_json_url,
                referer=f"{_DANIREON_BASE_URL}/",
            )
            json_quotes = parse_danireon_product_json(
                product_json=product_json,
                product_url=product_url,
                requested_card=requested_card,
            )

            if json_quotes:
                return json_quotes
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {403, 429}:
                raise
        except Exception:
            pass

        product_html = self._http_client.get_text(
            product_url,
            referer=f"{_DANIREON_BASE_URL}/",
        )

        return parse_danireon_product_page(
            html=product_html,
            product_url=product_url,
            requested_card=requested_card,
        )


def parse_danireon_product_json(
    product_json: dict[str, Any],
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    return parse_shopify_condition_variants(
        product_json,
        product_url,
        requested_card,
        store_id="danireon",
        extract_card_name_from_title=_extract_card_name_from_title,
        extract_collector_number=_extract_collector_number_from_title,
        extract_set_code=_extract_set_code_from_title,
        default_finish_from_title=_extract_finish,
    )


def parse_danireon_product_page(
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
    finish = _extract_finish(title)
    set_code, collector_number = _extract_set_and_collector_number(title)

    quotes: list[StoreQuote] = []
    seen: set[tuple[CardCondition, Decimal | None, bool]] = set()

    for match in _CONDITION_PATTERN.finditer(page_text):
        condition_label = _normalize_condition_label(match.group("condition"))
        condition = _CONDITION_LABELS[condition_label]

        price_text = match.group("price")
        price = Decimal(price_text) if price_text is not None else None

        sold_out = bool(match.group("sold_out_without_price")) or bool(
            match.group("sold_out_with_price")
        )
        in_stock = not sold_out and price is not None

        dedupe_key = (condition, price, in_stock)
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        quotes.append(
            StoreQuote(
                store_id="danireon",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=matched_card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=in_stock,
                product_url=product_url,
                set_code=set_code,
                collector_number=collector_number,
                raw_title=title,
                confidence_score=1.0,
            )
        )

    return quotes


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
    before_set_info = title.split("(", maxsplit=1)[0]
    return before_set_info.strip()


def _extract_collector_number_from_title(title: str) -> str | None:
    _, collector_number = _extract_set_and_collector_number(title)
    return collector_number


def _extract_set_code_from_title(title: str) -> str | None:
    set_code, _ = _extract_set_and_collector_number(title)
    return set_code


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _extract_finish(title: str) -> Finish:
    if " foil" in title.lower():
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_set_and_collector_number(title: str) -> tuple[str | None, str | None]:
    matches = list(_SET_AND_COLLECTOR_PATTERN.finditer(title))

    if not matches:
        return None, None

    match = matches[-1]
    return match.group("set_code"), match.group("collector_number")


def _normalize_condition_label(label: str) -> str:
    normalized = _simple_normalize(label)

    for known_label in _CONDITION_LABELS:
        if _simple_normalize(known_label) == normalized:
            return known_label

    raise ValueError(f"Unknown Danireon condition label: {label}")
