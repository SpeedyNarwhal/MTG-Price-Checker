from decimal import Decimal

import pytest
import requests

from mtg_price_checker.domain.enums import CardCondition, Finish, ResultStatus
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.services.price_checker import (
    build_price_result,
    check_prices,
    choose_lowest_nm_in_stock_quote,
)
from mtg_price_checker.stores.base import StoreAdapter


class BatchTestStore(StoreAdapter):
    def __init__(self) -> None:
        self.preloaded_cards: list[RequestedCard] = []
        self.search_calls: list[RequestedCard] = []

    @property
    def store_id(self) -> str:
        return "batchtest"

    @property
    def display_name(self) -> str:
        return "Batch Test"

    def preload_cards(self, requested_cards: list[RequestedCard]) -> None:
        self.preloaded_cards = requested_cards

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        self.search_calls.append(requested_card)
        return []


class FailingHttpStore(StoreAdapter):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.call_count = 0

    @property
    def store_id(self) -> str:
        return "failing"

    @property
    def display_name(self) -> str:
        return "Failing"

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        self.call_count += 1
        raise _http_error(self.status_code)


class SuccessfulStore(StoreAdapter):
    def __init__(self) -> None:
        self.call_count = 0

    @property
    def store_id(self) -> str:
        return "successful"

    @property
    def display_name(self) -> str:
        return "Successful"

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        self.call_count += 1
        return [
            StoreQuote(
                store_id=self.store_id,
                requested_card_name=requested_card.normalized_name,
                matched_card_name=requested_card.normalized_name,
                condition=CardCondition.NEAR_MINT,
                finish=Finish.NONFOIL,
                price_cad=Decimal("1.00"),
                in_stock=True,
            )
        ]


def test_choose_lowest_nm_in_stock_quote() -> None:
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    quotes = [
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.NEAR_MINT,
            finish=Finish.NONFOIL,
            price_cad=Decimal("2.00"),
            in_stock=True,
        ),
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.NEAR_MINT,
            finish=Finish.NONFOIL,
            price_cad=Decimal("1.50"),
            in_stock=True,
        ),
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.LIGHTLY_PLAYED,
            finish=Finish.NONFOIL,
            price_cad=Decimal("1.00"),
            in_stock=True,
        ),
    ]

    best_quote = choose_lowest_nm_in_stock_quote(requested_card, quotes)

    assert best_quote is not None
    assert best_quote.price_cad == Decimal("1.50")


def test_choose_lowest_in_stock_quote_respects_min_condition() -> None:
    from mtg_price_checker.services.price_checker import choose_lowest_in_stock_quote

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
        min_condition=CardCondition.LIGHTLY_PLAYED,
    )
    quotes = [
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.NEAR_MINT,
            finish=Finish.NONFOIL,
            price_cad=Decimal("2.00"),
            in_stock=True,
        ),
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.LIGHTLY_PLAYED,
            finish=Finish.NONFOIL,
            price_cad=Decimal("1.00"),
            in_stock=True,
        ),
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.MODERATELY_PLAYED,
            finish=Finish.NONFOIL,
            price_cad=Decimal("0.50"),
            in_stock=True,
        ),
    ]

    best_quote = choose_lowest_in_stock_quote(requested_card, quotes)

    assert best_quote is not None
    assert best_quote.price_cad == Decimal("1.00")
    assert best_quote.condition == CardCondition.LIGHTLY_PLAYED


def test_build_price_result_returns_not_found_when_no_quotes() -> None:
    requested_card = RequestedCard(input_name="Missing Card", normalized_name="Missing Card")

    result = build_price_result(requested_card, "test", [])

    assert result.status == ResultStatus.NOT_FOUND


def test_build_price_result_returns_out_of_stock_when_no_nm_in_stock() -> None:
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    quotes = [
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.NEAR_MINT,
            finish=Finish.NONFOIL,
            price_cad=Decimal("1.50"),
            in_stock=False,
        )
    ]

    result = build_price_result(requested_card, "test", quotes)

    assert result.status == ResultStatus.OUT_OF_STOCK


def test_build_price_result_returns_found_for_nm_in_stock() -> None:
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    quotes = [
        StoreQuote(
            store_id="test",
            requested_card_name="Sol Ring",
            matched_card_name="Sol Ring",
            condition=CardCondition.NEAR_MINT,
            finish=Finish.NONFOIL,
            price_cad=Decimal("1.50"),
            in_stock=True,
        )
    ]

    result = build_price_result(requested_card, "test", quotes)

    assert result.status == ResultStatus.FOUND
    assert result.lowest_nm_price_cad == Decimal("1.50")


def test_check_prices_preloads_batch_store_before_per_card_search() -> None:
    requested_cards = [
        RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet"),
    ]
    store = BatchTestStore()

    check_prices(requested_cards, [store])

    assert store.preloaded_cards == requested_cards
    assert store.search_calls == requested_cards


@pytest.mark.parametrize("status_code", [403, 429])
def test_check_prices_disables_store_after_http_403_or_429(status_code: int) -> None:
    requested_cards = [
        RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet"),
    ]
    store = FailingHttpStore(status_code)

    results = check_prices(requested_cards, [store])

    first_result = results["Sol Ring"]["failing"]
    second_result = results["Arcane Signet"]["failing"]

    assert store.call_count == 1
    assert first_result.status == ResultStatus.ERROR
    assert f"{status_code} Client Error" in (first_result.notes or "")
    assert second_result.status == ResultStatus.ERROR
    assert second_result.notes == f"Store disabled for this run after HTTP {status_code}."


class PricedStore(StoreAdapter):
    def __init__(self, store_id: str, display_name: str, price: str) -> None:
        self._store_id = store_id
        self._display_name = display_name
        self._price = Decimal(price)

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def display_name(self) -> str:
        return self._display_name

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        return [
            StoreQuote(
                store_id=self.store_id,
                requested_card_name=requested_card.normalized_name,
                matched_card_name=requested_card.normalized_name,
                condition=CardCondition.NEAR_MINT,
                finish=Finish.NONFOIL,
                price_cad=self._price,
                in_stock=True,
            )
        ]


def test_check_prices_parallel_matches_sequential_results() -> None:
    requested_cards = [
        RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet"),
    ]
    stores = [
        PricedStore("store-a", "Store A", "1.00"),
        PricedStore("store-b", "Store B", "2.00"),
    ]

    sequential_results = check_prices(requested_cards, stores, parallel_stores=False)
    parallel_results = check_prices(requested_cards, stores, parallel_stores=True)

    assert parallel_results == sequential_results


def test_check_prices_parallel_circuit_breaker_is_thread_safe() -> None:
    requested_cards = [
        RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet"),
    ]
    failing_store = FailingHttpStore(403)
    successful_store = SuccessfulStore()

    results = check_prices(
        requested_cards,
        [failing_store, successful_store],
        parallel_stores=True,
    )

    assert failing_store.call_count == 1
    assert successful_store.call_count == 2
    assert results["Sol Ring"]["failing"].status == ResultStatus.ERROR
    assert results["Arcane Signet"]["failing"].status == ResultStatus.ERROR
    assert results["Sol Ring"]["successful"].status == ResultStatus.FOUND
    assert results["Arcane Signet"]["successful"].status == ResultStatus.FOUND


def test_check_prices_disabled_store_does_not_stop_other_stores() -> None:
    requested_cards = [
        RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
        RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet"),
    ]
    failing_store = FailingHttpStore(403)
    successful_store = SuccessfulStore()

    results = check_prices(requested_cards, [failing_store, successful_store])

    assert failing_store.call_count == 1
    assert successful_store.call_count == 2
    assert results["Sol Ring"]["failing"].status == ResultStatus.ERROR
    assert (
        results["Arcane Signet"]["failing"].notes == "Store disabled for this run after HTTP 403."
    )
    assert results["Sol Ring"]["successful"].status == ResultStatus.FOUND
    assert results["Arcane Signet"]["successful"].status == ResultStatus.FOUND


def _http_error(status_code: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response.url = "https://example.test/search"

    return requests.HTTPError(f"{status_code} Client Error: Forbidden for url", response=response)
