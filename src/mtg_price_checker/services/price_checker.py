from mtg_price_checker.domain.enums import CardCondition, Finish, ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.stores.base import StoreAdapter


def choose_lowest_nm_in_stock_quote(
    requested_card: RequestedCard,
    quotes: list[StoreQuote],
) -> StoreQuote | None:
    valid_quotes = [
        quote
        for quote in quotes
        if quote.in_stock
        and quote.condition == CardCondition.NEAR_MINT
        and _finish_matches(requested_card.finish_preference, quote.finish)
    ]

    if not valid_quotes:
        return None

    return min(valid_quotes, key=lambda quote: quote.price_cad)


def build_price_result(
    requested_card: RequestedCard,
    store_id: str,
    quotes: list[StoreQuote],
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

    return PriceResult(
        requested_card=requested_card,
        store_id=store_id,
        status=ResultStatus.FOUND,
        lowest_nm_price_cad=best_quote.price_cad,
        product_url=best_quote.product_url,
    )


def check_prices(
    requested_cards: list[RequestedCard],
    stores: list[StoreAdapter],
) -> dict[str, dict[str, PriceResult]]:
    results: dict[str, dict[str, PriceResult]] = {}

    for card in requested_cards:
        card_results: dict[str, PriceResult] = {}

        for store in stores:
            try:
                quotes = store.search_card(card)
                result = build_price_result(card, store.store_id, quotes)
            except Exception as exc:
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
