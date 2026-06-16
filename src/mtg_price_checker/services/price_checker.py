from decimal import Decimal

import requests

from mtg_price_checker.domain.enums import CardCondition, Finish, ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.stores.base import BatchStoreAdapter, StoreAdapter


def choose_lowest_nm_in_stock_quote(
    requested_card: RequestedCard,
    quotes: list[StoreQuote],
) -> StoreQuote | None:
    valid_quotes = [
        quote
        for quote in quotes
        if quote.in_stock
        and quote.price_cad is not None
        and quote.condition == CardCondition.NEAR_MINT
        and _finish_matches(requested_card.finish_preference, quote.finish)
    ]

    if not valid_quotes:
        return None

    return min(valid_quotes, key=_required_price)


def build_price_result(
    requested_card: RequestedCard,
    store_id: str,
    quotes: list[StoreQuote],
    *,
    listings_checked: int | None = None,
) -> PriceResult:
    if not quotes:
        return PriceResult(
            requested_card=requested_card,
            store_id=store_id,
            status=ResultStatus.NOT_FOUND,
            notes="No matching listing found.",
        )

    best_quote = choose_lowest_nm_in_stock_quote(requested_card, quotes)

    if best_quote is None:
        return PriceResult(
            requested_card=requested_card,
            store_id=store_id,
            status=ResultStatus.OUT_OF_STOCK,
            notes="Listings found, but no NM in-stock copy matched preferences.",
        )

    notes = None
    if listings_checked is not None and listings_checked > 0:
        notes = f"Checked {listings_checked} product listings."

    return PriceResult(
        requested_card=requested_card,
        store_id=store_id,
        status=ResultStatus.FOUND,
        lowest_nm_price_cad=best_quote.price_cad,
        product_url=best_quote.product_url,
        notes=notes,
    )


def check_prices(
    requested_cards: list[RequestedCard],
    stores: list[StoreAdapter],
) -> dict[str, dict[str, PriceResult]]:
    results: dict[str, dict[str, PriceResult]] = {}
    preload_errors: dict[str, Exception] = {}
    disabled_store_status_codes: dict[str, int] = {}

    for store in stores:
        if not isinstance(store, BatchStoreAdapter):
            continue

        try:
            store.preload_cards(requested_cards)
        except Exception as exc:
            preload_errors[store.store_id] = exc

            status_code = _circuit_breaker_status_code(exc)
            if status_code is not None:
                disabled_store_status_codes[store.store_id] = status_code

    for card in requested_cards:
        card_results: dict[str, PriceResult] = {}

        for store in stores:
            disabled_status_code = disabled_store_status_codes.get(store.store_id)

            if disabled_status_code is not None:
                card_results[store.store_id] = PriceResult(
                    requested_card=card,
                    store_id=store.store_id,
                    status=ResultStatus.ERROR,
                    notes=_store_disabled_note(disabled_status_code),
                )
                continue

            try:
                preload_error = preload_errors.get(store.store_id)

                if preload_error is not None:
                    raise preload_error

                quotes = store.search_card(card)
                listings_checked = store.last_listings_checked
                result = build_price_result(
                    card,
                    store.store_id,
                    quotes,
                    listings_checked=listings_checked,
                )
            except Exception as exc:
                status_code = _circuit_breaker_status_code(exc)

                if status_code is not None:
                    disabled_store_status_codes[store.store_id] = status_code

                result = PriceResult(
                    requested_card=card,
                    store_id=store.store_id,
                    status=ResultStatus.ERROR,
                    notes=str(exc),
                )

            card_results[store.store_id] = result

        results[card.normalized_name] = card_results

    return results


def _finish_matches(preference: Finish, actual: Finish) -> bool:
    if preference == Finish.EITHER:
        return True

    return preference == actual


def _required_price(quote: StoreQuote) -> Decimal:
    if quote.price_cad is None:
        raise ValueError("Expected quote to have a price.")
    return quote.price_cad


def _circuit_breaker_status_code(exc: Exception) -> int | None:
    if not isinstance(exc, requests.HTTPError):
        return None

    if exc.response is None:
        return None

    if exc.response.status_code in {403, 429}:
        return exc.response.status_code

    return None


def _store_disabled_note(status_code: int) -> str:
    return f"Store disabled for this run after HTTP {status_code}."
