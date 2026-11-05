from decimal import Decimal

from mtg_price_checker.app.serialize import serialize_job_results, serialize_progress_event
from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.progress import ProgressEvent
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.fake import build_demo_stores


def test_serialize_progress_event() -> None:
    event = ProgressEvent(
        card_index=1,
        total_cards=3,
        card_name="Sol Ring",
        message="[1/3] Sol Ring — Demo FOUND",
        store_statuses={"demo": "FOUND"},
    )

    payload = serialize_progress_event(event)

    assert payload["type"] == "progress"
    assert payload["card_index"] == 1
    assert payload["store_statuses"]["demo"] == "FOUND"


def test_serialize_job_results_includes_prices() -> None:
    stores = build_demo_stores()
    card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")
    results = {
        "Sol Ring": {
            stores[0].store_id: PriceResult(
                requested_card=card,
                store_id=stores[0].store_id,
                status=ResultStatus.FOUND,
                lowest_nm_price_cad=Decimal("1.99"),
                product_url="https://example.com/sol-ring",
            )
        }
    }

    payload = serialize_job_results([card], stores[:1], results)

    assert payload["stores"][0]["store_id"] == stores[0].store_id
    assert payload["cards"][0]["stores"][0]["price_cad"] == "1.99"
    assert payload["cards"][0]["stores"][0]["status"] == "FOUND"
