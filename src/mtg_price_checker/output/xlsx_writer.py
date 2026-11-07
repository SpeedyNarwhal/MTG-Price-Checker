from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Protocol

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.output.formatting import format_price_cell

_DONT_BUY = "__dont_buy__"
_DONT_BUY_LABEL = "Don't buy"
_CURRENCY_FORMAT = '"$"#,##0.00'
_HEADER_FONT = Font(bold=True)
_LINK_FONT = Font(color="0563C1", underline="single")


class StoreLike(Protocol):
    @property
    def store_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...


@dataclass(frozen=True)
class ExportStore:
    store_id: str
    display_name: str


def write_results_xlsx(
    output_path: Path,
    requested_cards: list[RequestedCard],
    stores: list[StoreLike],
    results: dict[str, dict[str, PriceResult]],
    picks: Mapping[str, str] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_results_workbook(
        requested_cards=requested_cards,
        stores=stores,
        results=results,
        picks=picks,
    )
    workbook.save(output_path)


def results_xlsx_bytes(
    requested_cards: list[RequestedCard],
    stores: list[StoreLike],
    results: dict[str, dict[str, PriceResult]],
    picks: Mapping[str, str] | None = None,
) -> bytes:
    workbook = build_results_workbook(
        requested_cards=requested_cards,
        stores=stores,
        results=results,
        picks=picks,
    )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_results_workbook(
    *,
    requested_cards: list[RequestedCard],
    stores: list[StoreLike],
    results: dict[str, dict[str, PriceResult]],
    picks: Mapping[str, str] | None = None,
) -> Workbook:
    workbook = Workbook()
    prices_sheet = workbook.active
    prices_sheet.title = "Prices"
    _write_prices_sheet(prices_sheet, requested_cards, stores, results, picks)

    shopping_sheet = workbook.create_sheet("Shopping Lists")
    _write_shopping_lists_sheet(
        shopping_sheet,
        requested_cards,
        stores,
        results,
        picks or {},
    )

    return workbook


def price_results_from_job_payload(
    payload: dict[str, Any],
    requested_cards: list[RequestedCard],
) -> tuple[list[ExportStore], dict[str, dict[str, PriceResult]]]:
    stores = [
        ExportStore(store_id=str(store["store_id"]), display_name=str(store["display_name"]))
        for store in payload.get("stores", [])
        if isinstance(store, dict)
    ]
    cards_by_name = {card.normalized_name: card for card in requested_cards}
    results: dict[str, dict[str, PriceResult]] = {
        card.normalized_name: {} for card in requested_cards
    }

    for card_row in payload.get("cards", []):
        if not isinstance(card_row, dict):
            continue
        card_name = str(card_row.get("card_name") or "")
        requested_card = cards_by_name.get(card_name)
        if requested_card is None:
            continue
        for cell in card_row.get("stores") or []:
            if not isinstance(cell, dict):
                continue
            store_id = str(cell.get("store_id") or "")
            if not store_id:
                continue
            raw_price = cell.get("price_cad")
            price = Decimal(str(raw_price)) if raw_price not in (None, "") else None
            status_value = str(cell.get("status") or ResultStatus.NOT_FOUND.value)
            try:
                status = ResultStatus(status_value)
            except ValueError:
                status = ResultStatus.ERROR
            results[card_name][store_id] = PriceResult(
                requested_card=requested_card,
                store_id=store_id,
                status=status,
                lowest_nm_price_cad=price,
                product_url=cell.get("product_url"),
                notes=cell.get("notes"),
            )

    return stores, results


def _write_prices_sheet(
    sheet: Worksheet,
    requested_cards: list[RequestedCard],
    stores: list[StoreLike],
    results: dict[str, dict[str, PriceResult]],
    picks: Mapping[str, str] | None,
) -> None:
    headers = ["Card", "Qty", *[store.display_name for store in stores], "Buy at"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = _HEADER_FONT

    store_by_id = {store.store_id: store for store in stores}
    buy_at_col = 3 + len(stores)
    first_data_row = 2
    last_data_row = first_data_row + len(requested_cards) - 1

    for card in requested_cards:
        buy_at = _buy_at_label(card.normalized_name, picks, store_by_id)
        row: list[Any] = [card.normalized_name, card.quantity]

        for store in stores:
            result = results[card.normalized_name][store.store_id]
            if result.status == ResultStatus.FOUND and result.lowest_nm_price_cad is not None:
                row.append(float(result.lowest_nm_price_cad))
            else:
                row.append(format_price_cell(result))

        row.append(buy_at)
        sheet.append(row)
        excel_row = sheet.max_row

        for store_index, store in enumerate(stores):
            result = results[card.normalized_name][store.store_id]
            column_index = 3 + store_index
            cell = sheet.cell(row=excel_row, column=column_index)
            if result.status == ResultStatus.FOUND and result.lowest_nm_price_cad is not None:
                cell.number_format = _CURRENCY_FORMAT
                if result.product_url:
                    cell.hyperlink = result.product_url
                    cell.font = _LINK_FONT

    if requested_cards:
        options = [_DONT_BUY_LABEL, *[store.display_name for store in stores]]
        # Excel list validation is comma-separated; escape by wrapping the whole list.
        formula = '"' + ",".join(options) + '"'
        validation = DataValidation(
            type="list",
            formula1=formula,
            allow_blank=True,
            showDropDown=False,
        )
        validation.error = "Pick a store from the list."
        validation.errorTitle = "Buy at"
        validation.prompt = "Choose where to buy this card."
        validation.promptTitle = "Buy at"
        sheet.add_data_validation(validation)
        buy_at_letter = get_column_letter(buy_at_col)
        validation.add(f"{buy_at_letter}{first_data_row}:{buy_at_letter}{last_data_row}")


def _write_shopping_lists_sheet(
    sheet: Worksheet,
    requested_cards: list[RequestedCard],
    stores: list[StoreLike],
    results: dict[str, dict[str, PriceResult]],
    picks: Mapping[str, str],
) -> None:
    headers = ["Store", "Qty", "Card", "Unit price", "Line total"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = _HEADER_FONT

    wrote_any = False
    for store in stores:
        store_subtotal = Decimal("0")
        store_rows: list[tuple[str, int, str, Decimal, Decimal]] = []

        for card in requested_cards:
            pick = picks.get(card.normalized_name)
            if pick != store.store_id:
                continue
            result = results[card.normalized_name].get(store.store_id)
            if (
                result is None
                or result.status != ResultStatus.FOUND
                or result.lowest_nm_price_cad is None
            ):
                continue
            unit_price = result.lowest_nm_price_cad
            line_total = unit_price * card.quantity
            store_subtotal += line_total
            store_rows.append(
                (
                    store.display_name,
                    card.quantity,
                    card.normalized_name,
                    unit_price,
                    line_total,
                )
            )

        if not store_rows:
            continue

        wrote_any = True
        for store_name, qty, card_name, unit_price, line_total in store_rows:
            sheet.append(
                [
                    store_name,
                    qty,
                    card_name,
                    float(unit_price),
                    float(line_total),
                ]
            )
            excel_row = sheet.max_row
            sheet.cell(row=excel_row, column=4).number_format = _CURRENCY_FORMAT
            sheet.cell(row=excel_row, column=5).number_format = _CURRENCY_FORMAT

        sheet.append([store.display_name, "", "Subtotal", "", float(store_subtotal)])
        subtotal_row = sheet.max_row
        sheet.cell(row=subtotal_row, column=3).font = _HEADER_FONT
        sheet.cell(row=subtotal_row, column=5).font = _HEADER_FONT
        sheet.cell(row=subtotal_row, column=5).number_format = _CURRENCY_FORMAT
        sheet.append([])

    if not wrote_any:
        sheet.append(["", "", "No FOUND picks yet.", "", ""])


def _buy_at_label(
    card_name: str,
    picks: Mapping[str, str] | None,
    store_by_id: dict[str, StoreLike],
) -> str:
    if picks is None:
        return _DONT_BUY_LABEL
    pick = picks.get(card_name)
    if pick is None or pick == _DONT_BUY or pick == "":
        return _DONT_BUY_LABEL
    store = store_by_id.get(pick)
    return store.display_name if store is not None else pick
