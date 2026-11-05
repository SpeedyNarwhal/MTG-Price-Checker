from decimal import Decimal
from typing import Any

from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.progress import ProgressEvent
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.base import StoreAdapter


def serialize_progress_event(event: ProgressEvent) -> dict[str, Any]:
    return {
        "type": "progress",
        "card_index": event.card_index,
        "total_cards": event.total_cards,
        "card_name": event.card_name,
        "message": event.message,
        "store_statuses": event.store_statuses,
    }


def serialize_price_result(result: PriceResult) -> dict[str, Any]:
    return {
        "card_name": result.requested_card.normalized_name,
        "quantity": result.requested_card.quantity,
        "store_id": result.store_id,
        "status": result.status.value,
        "price_cad": _decimal_to_str(result.lowest_nm_price_cad),
        "product_url": result.product_url,
        "notes": result.notes,
    }


def serialize_job_results(
    requested_cards: list[RequestedCard],
    stores: list[StoreAdapter],
    results: dict[str, dict[str, PriceResult]],
) -> dict[str, Any]:
    store_meta = [
        {"store_id": store.store_id, "display_name": store.display_name} for store in stores
    ]
    cards: list[dict[str, Any]] = []

    for card in requested_cards:
        card_results = results.get(card.normalized_name, {})
        cells = []
        for store in stores:
            result = card_results.get(store.store_id)
            if result is None:
                cells.append(
                    {
                        "store_id": store.store_id,
                        "status": "NOT_FOUND",
                        "price_cad": None,
                        "product_url": None,
                        "notes": None,
                    }
                )
            else:
                cells.append(
                    {
                        "store_id": store.store_id,
                        "status": result.status.value,
                        "price_cad": _decimal_to_str(result.lowest_nm_price_cad),
                        "product_url": result.product_url,
                        "notes": result.notes,
                    }
                )

        cards.append(
            {
                "card_name": card.normalized_name,
                "quantity": card.quantity,
                "stores": cells,
            }
        )

    return {"stores": store_meta, "cards": cards}


def _decimal_to_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{value:.2f}"
