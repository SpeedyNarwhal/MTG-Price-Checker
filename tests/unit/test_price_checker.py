from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish, ResultStatus
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.services.price_checker import (
    build_price_result,
    choose_lowest_nm_in_stock_quote,
)


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
