import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import requests

from mtg_price_checker.domain.conditions import condition_meets_minimum
from mtg_price_checker.domain.enums import Finish, ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.progress import ProgressEvent
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.stores.base import BatchStoreAdapter, StoreAdapter

_PROGRESS_THRESHOLD = 20

ProgressCallback = Callable[[ProgressEvent], None]
CancelCallback = Callable[[], bool]


def choose_lowest_in_stock_quote(
    requested_card: RequestedCard,
    quotes: list[StoreQuote],
) -> StoreQuote | None:
    valid_quotes = [
        quote
        for quote in quotes
        if quote.in_stock
        and quote.price_cad is not None
        and condition_meets_minimum(quote.condition, requested_card.min_condition)
        and _finish_matches(requested_card.finish_preference, quote.finish)
    ]

    if not valid_quotes:
        return None

    return min(valid_quotes, key=_required_price)


def choose_lowest_nm_in_stock_quote(
    requested_card: RequestedCard,
    quotes: list[StoreQuote],
) -> StoreQuote | None:
    """Backward-compatible alias for choose_lowest_in_stock_quote."""
    return choose_lowest_in_stock_quote(requested_card, quotes)


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

    best_quote = choose_lowest_in_stock_quote(requested_card, quotes)

    if best_quote is None:
        return PriceResult(
            requested_card=requested_card,
            store_id=store_id,
            status=ResultStatus.OUT_OF_STOCK,
            notes=(
                "Listings found, but no in-stock copy matched condition/finish preferences "
                f"(min condition {requested_card.min_condition.value})."
            ),
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
    *,
    parallel_stores: bool = False,
    show_progress: bool | None = None,
    on_progress: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> dict[str, dict[str, PriceResult]]:
    results: dict[str, dict[str, PriceResult]] = {}
    preload_errors: dict[str, Exception] = {}
    disabled_store_status_codes: dict[str, int] = {}
    circuit_breaker_lock = threading.Lock()

    progress_callback = on_progress
    if progress_callback is None:
        should_show_progress = (
            len(requested_cards) > _PROGRESS_THRESHOLD if show_progress is None else show_progress
        )
        if should_show_progress:
            progress_callback = _stderr_progress_callback

    for store in stores:
        if not isinstance(store, BatchStoreAdapter):
            continue

        if should_cancel is not None and should_cancel():
            return results

        try:
            store.preload_cards(requested_cards)
        except Exception as exc:
            preload_errors[store.store_id] = exc

            status_code = _circuit_breaker_status_code(exc)
            if status_code is not None:
                disabled_store_status_codes[store.store_id] = status_code

    for card_index, card in enumerate(requested_cards, start=1):
        if should_cancel is not None and should_cancel():
            return results

        if parallel_stores and len(stores) > 1:
            card_results = _check_card_parallel(
                card=card,
                stores=stores,
                preload_errors=preload_errors,
                disabled_store_status_codes=disabled_store_status_codes,
                circuit_breaker_lock=circuit_breaker_lock,
            )
        else:
            card_results = _check_card_sequential(
                card=card,
                stores=stores,
                preload_errors=preload_errors,
                disabled_store_status_codes=disabled_store_status_codes,
            )

        results[card.normalized_name] = card_results

        if progress_callback is not None:
            progress_callback(
                _build_progress_event(
                    card_index=card_index,
                    total_cards=len(requested_cards),
                    card=card,
                    stores=stores,
                    card_results=card_results,
                )
            )

    return results


def _check_card_sequential(
    card: RequestedCard,
    stores: list[StoreAdapter],
    preload_errors: dict[str, Exception],
    disabled_store_status_codes: dict[str, int],
) -> dict[str, PriceResult]:
    card_results: dict[str, PriceResult] = {}

    for store in stores:
        card_results[store.store_id] = _query_store_for_card(
            card=card,
            store=store,
            preload_errors=preload_errors,
            disabled_store_status_codes=disabled_store_status_codes,
            circuit_breaker_lock=None,
        )

    return card_results


def _check_card_parallel(
    card: RequestedCard,
    stores: list[StoreAdapter],
    preload_errors: dict[str, Exception],
    disabled_store_status_codes: dict[str, int],
    circuit_breaker_lock: threading.Lock,
) -> dict[str, PriceResult]:
    card_results: dict[str, PriceResult] = {}

    with ThreadPoolExecutor(max_workers=len(stores)) as executor:
        futures = {
            executor.submit(
                _query_store_for_card,
                card,
                store,
                preload_errors,
                disabled_store_status_codes,
                circuit_breaker_lock,
            ): store
            for store in stores
        }

        for future in futures:
            store = futures[future]
            card_results[store.store_id] = future.result()

    return card_results


def _query_store_for_card(
    card: RequestedCard,
    store: StoreAdapter,
    preload_errors: dict[str, Exception],
    disabled_store_status_codes: dict[str, int],
    circuit_breaker_lock: threading.Lock | None,
) -> PriceResult:
    disabled_status_code = _get_disabled_status_code(
        store.store_id,
        disabled_store_status_codes,
        circuit_breaker_lock,
    )

    if disabled_status_code is not None:
        return PriceResult(
            requested_card=card,
            store_id=store.store_id,
            status=ResultStatus.ERROR,
            notes=_store_disabled_note(disabled_status_code),
        )

    try:
        preload_error = _get_preload_error(
            store.store_id,
            preload_errors,
            circuit_breaker_lock,
        )

        if preload_error is not None:
            raise preload_error

        quotes = store.search_card(card)
        listings_checked = store.last_listings_checked

        return build_price_result(
            card,
            store.store_id,
            quotes,
            listings_checked=listings_checked,
        )
    except Exception as exc:
        status_code = _circuit_breaker_status_code(exc)

        if status_code is not None:
            _set_disabled_status_code(
                store.store_id,
                status_code,
                disabled_store_status_codes,
                circuit_breaker_lock,
            )

        return PriceResult(
            requested_card=card,
            store_id=store.store_id,
            status=ResultStatus.ERROR,
            notes=str(exc),
        )


def _get_disabled_status_code(
    store_id: str,
    disabled_store_status_codes: dict[str, int],
    circuit_breaker_lock: threading.Lock | None,
) -> int | None:
    if circuit_breaker_lock is None:
        return disabled_store_status_codes.get(store_id)

    with circuit_breaker_lock:
        return disabled_store_status_codes.get(store_id)


def _get_preload_error(
    store_id: str,
    preload_errors: dict[str, Exception],
    circuit_breaker_lock: threading.Lock | None,
) -> Exception | None:
    if circuit_breaker_lock is None:
        return preload_errors.get(store_id)

    with circuit_breaker_lock:
        return preload_errors.get(store_id)


def _set_disabled_status_code(
    store_id: str,
    status_code: int,
    disabled_store_status_codes: dict[str, int],
    circuit_breaker_lock: threading.Lock | None,
) -> None:
    if circuit_breaker_lock is None:
        disabled_store_status_codes[store_id] = status_code
        return

    with circuit_breaker_lock:
        disabled_store_status_codes[store_id] = status_code


def _build_progress_event(
    card_index: int,
    total_cards: int,
    card: RequestedCard,
    stores: list[StoreAdapter],
    card_results: dict[str, PriceResult],
) -> ProgressEvent:
    store_statuses = {store.store_id: card_results[store.store_id].status.value for store in stores}
    summaries = [
        f"{store.display_name} {card_results[store.store_id].status.value}" for store in stores
    ]
    summary_text = ", ".join(summaries)
    message = f"[{card_index}/{total_cards}] {card.normalized_name} — {summary_text}"

    return ProgressEvent(
        card_index=card_index,
        total_cards=total_cards,
        card_name=card.normalized_name,
        message=message,
        store_statuses=store_statuses,
    )


def _stderr_progress_callback(event: ProgressEvent) -> None:
    print(event.message, file=sys.stderr)


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
