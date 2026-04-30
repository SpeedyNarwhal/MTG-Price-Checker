import csv
from pathlib import Path

from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.base import StoreAdapter


def write_price_matrix_csv(
    output_path: Path,
    requested_cards: list[RequestedCard],
    stores: list[StoreAdapter],
    results: dict[str, dict[str, PriceResult]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["Card", *[store.display_name for store in stores]]

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for card in requested_cards:
            row = {"Card": card.normalized_name}

            for store in stores:
                result = results[card.normalized_name][store.store_id]
                row[store.display_name] = _format_cell(result)

            writer.writerow(row)


def _format_cell(result: PriceResult) -> str:
    if result.status == ResultStatus.FOUND and result.lowest_nm_price_cad is not None:
        return f"${result.lowest_nm_price_cad:.2f}"

    return result.status.value