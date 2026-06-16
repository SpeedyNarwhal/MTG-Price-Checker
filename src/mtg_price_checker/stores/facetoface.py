import re
from decimal import Decimal
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import StoreAdapter

_FACE_TO_FACE_BASE_URL = "https://facetofacegames.com"
_DECK_BUILDER_SEARCH_URL = f"{_FACE_TO_FACE_BASE_URL}/apps/prod-indexer/deckBuilder/search"

_CONDITION_LABELS = {
    "NM": CardCondition.NEAR_MINT,
    "NEAR MINT": CardCondition.NEAR_MINT,
    "PL": CardCondition.LIGHTLY_PLAYED,
    "LIGHTLY PLAYED": CardCondition.LIGHTLY_PLAYED,
    "MP": CardCondition.MODERATELY_PLAYED,
    "MODERATELY PLAYED": CardCondition.MODERATELY_PLAYED,
    "HP": CardCondition.HEAVILY_PLAYED,
    "HEAVILY PLAYED": CardCondition.HEAVILY_PLAYED,
    "DMG": CardCondition.DAMAGED,
    "DAMAGED": CardCondition.DAMAGED,
}

_CONDITION_PATTERN = re.compile(
    r"(?P<label>NM|PL|MP|HP|DMG)\s*"
    r"\((?P<quantity>\d+)\)"
    r"[\s\S]{0,300}?"
    r"Regular price\s+\$(?P<price>\d+(?:\.\d{2})?)",
    re.IGNORECASE,
)

_SET_PATTERN = re.compile(r"Set:\s*(?P<set_name>[\s\S]+?)\s+Type Line:", re.IGNORECASE)
_COLLECTOR_PATTERN = re.compile(r"Collector #:\s*(?P<collector_number>[A-Z0-9\-]+)", re.IGNORECASE)
_FINISH_PATTERN = re.compile(r"Finish:\s*(?P<finish>Non-Foil|Foil)", re.IGNORECASE)


class FaceToFaceStoreAdapter(StoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 5,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check
        self._quotes_by_card_name: dict[str, list[StoreQuote]] = {}
        self._preloaded_card_names: set[str] = set()

    @property
    def store_id(self) -> str:
        return "facetoface"

    @property
    def display_name(self) -> str:
        return "Face to Face"

    def preload_cards(self, requested_cards: list[RequestedCard]) -> None:
        unique_cards_by_key = {
            _card_cache_key(requested_card): requested_card for requested_card in requested_cards
        }

        if not unique_cards_by_key:
            return

        deck_builder_response = self._http_client.post_json(
            _DECK_BUILDER_SEARCH_URL,
            _build_deck_builder_payload(
                [card.normalized_name for card in unique_cards_by_key.values()]
            ),
        )

        cards = _safe_dict(deck_builder_response, "Cards")

        for normalized_key, requested_card in unique_cards_by_key.items():
            self._quotes_by_card_name[normalized_key] = (
                parse_face_to_face_deck_builder_cards(
                    cards=cards,
                    requested_card=requested_card,
                    max_products_to_check=self._max_products_to_check,
                )
                if cards is not None
                else []
            )
            self._preloaded_card_names.add(normalized_key)

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        normalized_key = _card_cache_key(requested_card)

        if normalized_key in self._preloaded_card_names:
            return self._quotes_by_card_name.get(normalized_key, [])

        try:
            self.preload_cards([requested_card])
            return self._quotes_by_card_name.get(normalized_key, [])

        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                raise

        except Exception:
            pass

        product_urls = self._search_product_urls_from_pages(requested_card)
        quotes: list[StoreQuote] = []

        for product_url in product_urls[: self._max_products_to_check]:
            product_html = self._http_client.get_text(product_url)
            quotes.extend(
                parse_face_to_face_product_page(
                    html=product_html,
                    product_url=product_url,
                    requested_card=requested_card,
                )
            )

        return quotes

    def _search_product_urls_from_pages(self, requested_card: RequestedCard) -> list[str]:
        search_html = self._http_client.get_text(
            f"{_FACE_TO_FACE_BASE_URL}/search",
            params={
                "q": requested_card.normalized_name,
                "type": "product",
            },
        )

        return _extract_product_urls(search_html)


def parse_face_to_face_deck_builder_response(
    payload: Any,
    requested_card: RequestedCard,
    max_products_to_check: int | None = None,
) -> list[StoreQuote]:
    cards = _safe_dict(payload, "Cards")

    return parse_face_to_face_deck_builder_cards(
        cards=cards,
        requested_card=requested_card,
        max_products_to_check=max_products_to_check,
    )


def parse_face_to_face_deck_builder_cards(
    cards: dict[Any, Any] | None,
    requested_card: RequestedCard,
    max_products_to_check: int | None = None,
) -> list[StoreQuote]:
    if cards is None:
        return []

    products = _find_card_products(cards, requested_card.normalized_name)

    if max_products_to_check is not None:
        products = products[:max_products_to_check]

    quotes: list[StoreQuote] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        source = _safe_dict(product, "_source")

        if source is None:
            continue

        card_name = _safe_string(source.get("General_Card_Name"))

        if card_name is None:
            continue

        if not _card_names_match(requested_card.normalized_name, card_name):
            continue

        handle = _safe_string(source.get("handle"))
        product_url = f"{_FACE_TO_FACE_BASE_URL}/products/{handle}" if handle else None
        set_name = _safe_string(source.get("MTG_Set_Name"))
        collector_number = _safe_string(source.get("MTG_Collector_Number"))
        finish = _finish_from_text(_safe_string(source.get("MTG_Foil_Option")) or "")
        variants = source.get("variants")

        if not isinstance(variants, list):
            continue

        for variant in variants:
            if not isinstance(variant, dict):
                continue

            condition = _extract_variant_condition(variant)
            price = _extract_variant_price(variant)
            quantity_available = _extract_variant_quantity(variant)

            if condition is None:
                continue

            quotes.append(
                StoreQuote(
                    store_id="facetoface",
                    requested_card_name=requested_card.normalized_name,
                    matched_card_name=card_name,
                    condition=condition,
                    finish=finish,
                    price_cad=price,
                    in_stock=quantity_available > 0 and price is not None,
                    product_url=product_url,
                    quantity_available=quantity_available,
                    set_name=set_name,
                    collector_number=collector_number,
                    raw_title=card_name,
                    confidence_score=1.0,
                )
            )

    return quotes


def parse_face_to_face_product_page(
    html: str,
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    soup = BeautifulSoup(html, "html.parser")

    card_name = _extract_card_name(soup)
    raw_title = _extract_raw_title(soup) or card_name

    if card_name is None:
        return []

    if not _card_names_match(requested_card.normalized_name, card_name):
        return []

    page_text = soup.get_text(" ", strip=True)

    finish = _extract_finish(page_text, raw_title)
    set_name = _extract_set_name(page_text)
    collector_number = _extract_collector_number(page_text)

    quotes: list[StoreQuote] = []
    seen: set[tuple[CardCondition, Decimal, int]] = set()

    for match in _CONDITION_PATTERN.finditer(page_text):
        label = match.group("label").upper()
        quantity = int(match.group("quantity"))
        price = Decimal(match.group("price"))
        condition = _CONDITION_LABELS[label]

        dedupe_key = (condition, price, quantity)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        quotes.append(
            StoreQuote(
                store_id="facetoface",
                requested_card_name=requested_card.normalized_name,
                matched_card_name=card_name,
                condition=condition,
                finish=finish,
                price_cad=price,
                in_stock=quantity > 0,
                product_url=product_url,
                quantity_available=quantity,
                set_name=set_name,
                collector_number=collector_number,
                raw_title=raw_title,
                confidence_score=1.0,
            )
        )

    return quotes


def _extract_product_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href_value = link.get("href")

        if not isinstance(href_value, str):
            continue

        if "/products/" not in href_value:
            continue

        absolute_url = urljoin(_FACE_TO_FACE_BASE_URL, href_value).split("?")[0]

        if absolute_url not in urls:
            urls.append(absolute_url)

    return urls


def _extract_card_name(soup: BeautifulSoup) -> str | None:
    heading = soup.find("h1")

    if heading is not None:
        card_name = heading.get_text(" ", strip=True)

        if card_name:
            return _strip_face_to_face_title_suffix(card_name)

    raw_title = _extract_raw_title(soup)

    if raw_title is not None:
        return _strip_face_to_face_title_suffix(raw_title)

    return None


def _extract_raw_title(soup: BeautifulSoup) -> str | None:
    meta_title = soup.find("meta", property="og:title")

    if meta_title is not None:
        content = meta_title.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()

    document_title = soup.find("title")

    if document_title is not None:
        title = document_title.get_text(" ", strip=True)

        if title:
            return title

    return None


def _strip_face_to_face_title_suffix(value: str) -> str:
    # Turns:
    # "Arcane Signet [237] [Commander 2020] [Non-Foil]"
    # into:
    # "Arcane Signet"
    before_bracket = value.split("[", maxsplit=1)[0]
    before_pipe = before_bracket.split("|", maxsplit=1)[0]
    return before_pipe.strip()


def _extract_finish(page_text: str, raw_title: str | None) -> Finish:
    match = _FINISH_PATTERN.search(page_text)

    if match is not None:
        return _finish_from_text(match.group("finish"))

    if raw_title is not None:
        return _finish_from_text(raw_title)

    return Finish.NONFOIL


def _build_deck_builder_payload(card_names: list[str]) -> dict[str, Any]:
    return {
        "sort": False,
        "filters": [
            {
                "field": "Card Name",
                "values": card_names,
            },
            {
                "field": "in_stock",
                "values": ["1"],
            },
        ],
    }


def _card_cache_key(requested_card: RequestedCard) -> str:
    return _simple_normalize(requested_card.normalized_name)


def _find_card_products(cards: dict[Any, Any], requested_card_name: str) -> list[Any]:
    exact_products = cards.get(requested_card_name)

    if isinstance(exact_products, list):
        return exact_products

    normalized_requested_name = _simple_normalize(requested_card_name)

    for card_name, products in cards.items():
        if not isinstance(card_name, str):
            continue

        if _simple_normalize(card_name) == normalized_requested_name and isinstance(products, list):
            return products

    return []


def _safe_dict(value: Any, key: str) -> dict[Any, Any] | None:
    if not isinstance(value, dict):
        return None

    nested_value = value.get(key)

    if isinstance(nested_value, dict):
        return nested_value

    return None


def _safe_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    if isinstance(value, int | float):
        return str(value)

    return None


def _extract_variant_condition(variant: dict[str, Any]) -> CardCondition | None:
    selected_options = variant.get("selectedOptions")

    if not isinstance(selected_options, list):
        return None

    for option in selected_options:
        if not isinstance(option, dict):
            continue

        name = _safe_string(option.get("name"))

        if name is None or _simple_normalize(name) != "condition":
            continue

        value = _safe_string(option.get("value"))

        if value is None:
            return None

        return _CONDITION_LABELS.get(_simple_normalize(value).upper())

    return None


def _extract_variant_price(variant: dict[str, Any]) -> Decimal | None:
    raw_price = variant.get("price")

    if isinstance(raw_price, int | float):
        return Decimal(str(raw_price))

    if isinstance(raw_price, str):
        cleaned = raw_price.replace("$", "").replace("CAD", "").strip()

        try:
            return Decimal(cleaned)
        except Exception:
            return None

    return None


def _extract_variant_quantity(variant: dict[str, Any]) -> int:
    raw_quantity = variant.get("inventoryQuantity")

    if isinstance(raw_quantity, int):
        return raw_quantity

    if isinstance(raw_quantity, str):
        try:
            return int(raw_quantity)
        except ValueError:
            return 0

    return 0


def _finish_from_text(value: str) -> Finish:
    normalized = value.lower()

    if re.search(r"\bnon[-\s]?foil\b", normalized):
        return Finish.NONFOIL

    if re.search(r"\bfoil\b", normalized):
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_set_name(page_text: str) -> str | None:
    match = _SET_PATTERN.search(page_text)

    if match is None:
        return None

    return match.group("set_name").strip()


def _extract_collector_number(page_text: str) -> str | None:
    match = _COLLECTOR_PATTERN.search(page_text)

    if match is None:
        return None

    return match.group("collector_number").strip()


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
