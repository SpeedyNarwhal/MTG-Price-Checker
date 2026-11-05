from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from mtg_price_checker.domain.conditions import parse_condition_label
from mtg_price_checker.domain.enums import Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import BatchStoreAdapter, StoreAdapter

_WIZARD_TOWER_BASE_URL = "https://store.wizardtower.com"
_LOOKUP_URL = f"{_WIZARD_TOWER_BASE_URL}/apps/deckbuilder/lookup"
_MAX_NAMES_PER_REQUEST = 100
_GAME = "magic"


class WizardTowerStoreAdapter(StoreAdapter, BatchStoreAdapter):
    def __init__(
        self,
        http_client: HttpClient | None = None,
        max_products_to_check: int = 100,
    ) -> None:
        self._http_client = http_client or HttpClient()
        self._max_products_to_check = max_products_to_check
        self._quotes_by_card_name: dict[str, list[StoreQuote]] = {}
        self._listings_checked_by_card_name: dict[str, int] = {}
        self._preloaded_card_names: set[str] = set()
        self._last_listings_checked = 0

    @property
    def store_id(self) -> str:
        return "wizardtower"

    @property
    def display_name(self) -> str:
        return "Wizard Tower"

    @property
    def last_listings_checked(self) -> int:
        return self._last_listings_checked

    def preload_cards(self, requested_cards: list[RequestedCard]) -> None:
        unique_cards_by_key = {
            _card_cache_key(requested_card): requested_card for requested_card in requested_cards
        }

        if not unique_cards_by_key:
            return

        ordered_cards = list(unique_cards_by_key.values())
        results_by_card_name: dict[str, dict[str, Any]] = {}

        for chunk in _chunked(ordered_cards, _MAX_NAMES_PER_REQUEST):
            payload = {
                "game": _GAME,
                "names": [card.normalized_name for card in chunk],
            }
            response = self._http_client.post_json(_LOOKUP_URL, payload)
            for result in _safe_list(response, "results"):
                if not isinstance(result, dict):
                    continue
                card_name = _safe_string(result.get("cardName"))
                if card_name is None:
                    continue
                results_by_card_name[_simple_normalize(card_name)] = result

        for normalized_key, requested_card in unique_cards_by_key.items():
            result = results_by_card_name.get(normalized_key)
            quotes, listings_checked = parse_wizard_tower_lookup_result(
                result=result,
                requested_card=requested_card,
            )
            self._quotes_by_card_name[normalized_key] = quotes
            self._listings_checked_by_card_name[normalized_key] = listings_checked
            self._preloaded_card_names.add(normalized_key)

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        normalized_key = _card_cache_key(requested_card)

        if normalized_key not in self._preloaded_card_names:
            self.preload_cards([requested_card])

        self._last_listings_checked = self._listings_checked_by_card_name.get(normalized_key, 0)
        return self._quotes_by_card_name.get(normalized_key, [])


def parse_wizard_tower_lookup_results(
    payload: Any,
    requested_card: RequestedCard,
) -> tuple[list[StoreQuote], int]:
    results = _safe_list(payload, "results")
    target_key = _simple_normalize(requested_card.normalized_name)

    for result in results:
        if not isinstance(result, dict):
            continue
        card_name = _safe_string(result.get("cardName"))
        if card_name is None:
            continue
        if _simple_normalize(card_name) != target_key:
            continue
        return parse_wizard_tower_lookup_result(result=result, requested_card=requested_card)

    return [], 0


def parse_wizard_tower_lookup_result(
    *,
    result: dict[str, Any] | None,
    requested_card: RequestedCard,
) -> tuple[list[StoreQuote], int]:
    if result is None:
        return [], 0

    match = _safe_string(result.get("match"))
    if match is None or match.lower() != "exact":
        return [], 0

    products = result.get("products")
    if not isinstance(products, list):
        return [], 0

    quotes: list[StoreQuote] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        title = _safe_string(product.get("title"))
        if title is None:
            continue
        if not _card_names_match(requested_card.normalized_name, title):
            continue

        full_title = _safe_string(product.get("full_title")) or title
        relative_url = _safe_string(product.get("url"))
        product_url = (
            urljoin(_WIZARD_TOWER_BASE_URL, relative_url) if relative_url is not None else None
        )
        set_name = _safe_string(product.get("card_set"))
        collector_number = _safe_string(product.get("collector_number"))
        finish = _finish_from_product(product, full_title)
        variants = product.get("variants")

        if not isinstance(variants, list):
            continue

        for variant in variants:
            if not isinstance(variant, dict):
                continue

            condition = parse_condition_label(_safe_string(variant.get("condition_code")) or "")
            if condition is None:
                continue

            price = _extract_price(variant.get("price"))
            quantity_available = _extract_quantity(variant.get("inventory_quantity"))
            available = variant.get("available")
            in_stock = bool(available) if isinstance(available, bool) else quantity_available > 0
            if price is None:
                in_stock = False

            quotes.append(
                StoreQuote(
                    store_id="wizardtower",
                    requested_card_name=requested_card.normalized_name,
                    matched_card_name=title,
                    condition=condition,
                    finish=finish,
                    price_cad=price,
                    in_stock=in_stock,
                    product_url=product_url,
                    quantity_available=quantity_available,
                    set_name=set_name,
                    collector_number=collector_number,
                    raw_title=full_title,
                    confidence_score=1.0,
                )
            )

    return quotes, len(products)


def _finish_from_product(product: dict[str, Any], full_title: str) -> Finish:
    tags = product.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if not isinstance(tag, dict):
                continue
            field = _safe_string(tag.get("field"))
            if field != "mtg_mtg_finish":
                continue
            return _finish_from_text(_safe_string(tag.get("value")) or "")

    return _finish_from_text(full_title)


def _finish_from_text(value: str) -> Finish:
    normalized = value.lower()

    if re.search(r"\bnon[-\s]?foil\b", normalized) or normalized == "regular":
        return Finish.NONFOIL

    if "foil" in normalized:
        return Finish.FOIL

    return Finish.NONFOIL


def _extract_price(raw_price: Any) -> Decimal | None:
    if isinstance(raw_price, bool):
        return None

    if isinstance(raw_price, (int, float)):
        return Decimal(str(raw_price))

    if isinstance(raw_price, str):
        cleaned = raw_price.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    return None


def _extract_quantity(raw_quantity: Any) -> int:
    if isinstance(raw_quantity, bool):
        return 0

    if isinstance(raw_quantity, int):
        return raw_quantity

    if isinstance(raw_quantity, float):
        return int(raw_quantity)

    if isinstance(raw_quantity, str):
        try:
            return int(raw_quantity)
        except ValueError:
            return 0

    return 0


def _chunked(items: list[RequestedCard], size: int) -> list[list[RequestedCard]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _card_cache_key(requested_card: RequestedCard) -> str:
    return _simple_normalize(requested_card.normalized_name)


def _card_names_match(requested_name: str, matched_name: str) -> bool:
    return _simple_normalize(requested_name) == _simple_normalize(matched_name)


def _simple_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _safe_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _safe_list(payload: Any, key: str) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    return value if isinstance(value, list) else []
