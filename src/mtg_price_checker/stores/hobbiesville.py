import re
from typing import Any

import requests

from mtg_price_checker.domain.enums import Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.infra.http_client import HttpClient
from mtg_price_checker.stores.base import StoreAdapter
from mtg_price_checker.stores.shopify_common import (
    parse_shopify_condition_variants,
    search_product_urls,
    to_shopify_product_json_url,
)

_HOBBIESVILLE_BASE_URL = "https://www.hobbiesville.com"

_SET_AND_COLLECTOR_PATTERN = re.compile(
    r"\((?P<set_code>[A-Z0-9]{2,5})-(?P<collector_number>[A-Z0-9]+)\)"
)


class HobbiesvilleStoreAdapter(StoreAdapter):
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
        return "hobbiesville"

    @property
    def display_name(self) -> str:
        return "Hobbiesville"

    @property
    def last_listings_checked(self) -> int:
        return self._last_listings_checked

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        product_urls = search_product_urls(
            self._http_client,
            _HOBBIESVILLE_BASE_URL,
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
        product_json_url = to_shopify_product_json_url(product_url, _HOBBIESVILLE_BASE_URL)

        try:
            product_json = self._http_client.get_json(
                product_json_url,
                referer=f"{_HOBBIESVILLE_BASE_URL}/",
            )
            return parse_hobbiesville_product_json(
                product_json=product_json,
                product_url=product_url,
                requested_card=requested_card,
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {403, 429}:
                raise
            return []
        except Exception:
            return []


def parse_hobbiesville_product_json(
    product_json: dict[str, Any],
    product_url: str,
    requested_card: RequestedCard,
) -> list[StoreQuote]:
    return parse_shopify_condition_variants(
        product_json,
        product_url,
        requested_card,
        store_id="hobbiesville",
        extract_card_name_from_title=_extract_card_name_from_title,
        extract_collector_number=_extract_collector_number_from_title,
        extract_set_code=_extract_set_code_from_title,
        default_finish_from_title=_extract_finish,
    )


def _extract_card_name_from_title(title: str) -> str:
    before_set_info = title.split("(", maxsplit=1)[0]
    return before_set_info.strip()


def _extract_collector_number_from_title(title: str) -> str | None:
    _, collector_number = _extract_set_and_collector_number(title)
    return collector_number


def _extract_set_code_from_title(title: str) -> str | None:
    set_code, _ = _extract_set_and_collector_number(title)
    return set_code


def _extract_set_and_collector_number(title: str) -> tuple[str | None, str | None]:
    matches = list(_SET_AND_COLLECTOR_PATTERN.finditer(title))

    if not matches:
        return None, None

    match = matches[-1]
    return match.group("set_code"), match.group("collector_number")


def _extract_finish(title: str) -> Finish:
    if re.search(r"\bfoil\b", title.lower()):
        return Finish.FOIL

    return Finish.NONFOIL
