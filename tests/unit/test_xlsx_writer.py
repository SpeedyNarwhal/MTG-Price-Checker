from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.price_result import PriceResult
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.output.xlsx_writer import (
    ExportStore,
    price_results_from_job_payload,
    write_results_xlsx,
)


def _card(name: str, quantity: int = 1) -> RequestedCard:
    return RequestedCard(input_name=name, normalized_name=name, quantity=quantity)


def _result(
    card: RequestedCard,
    store_id: str,
    *,
    status: ResultStatus = ResultStatus.FOUND,
    price: str | None = "1.50",
    product_url: str | None = "https://example.com/p",
    notes: str | None = None,
) -> PriceResult:
    return PriceResult(
        requested_card=card,
        store_id=store_id,
        status=status,
        lowest_nm_price_cad=Decimal(price) if price is not None else None,
        product_url=product_url,
        notes=notes,
    )


def test_write_results_xlsx_prices_layout_links_dropdown_and_static_lists(
    tmp_path: Path,
) -> None:
    sol_ring = _card("Sol Ring", quantity=2)
    stores = [
        ExportStore(store_id="wizardtower", display_name="Wizard Tower"),
        ExportStore(store_id="facetoface", display_name="Face to Face"),
    ]
    results = {
        "Sol Ring": {
            "wizardtower": _result(
                sol_ring,
                "wizardtower",
                price="2.00",
                product_url="https://store.example/sol-ring",
            ),
            "facetoface": _result(
                sol_ring,
                "facetoface",
                status=ResultStatus.OUT_OF_STOCK,
                price=None,
                product_url=None,
            ),
        }
    }
    output_path = tmp_path / "prices.xlsx"

    write_results_xlsx(output_path, [sol_ring], stores, results)

    workbook = load_workbook(output_path)
    assert workbook.sheetnames == ["Prices", "Shopping Lists"]

    prices = workbook["Prices"]
    assert [cell.value for cell in prices[1]] == [
        "Card",
        "Qty",
        "Wizard Tower",
        "Face to Face",
        "Buy at",
    ]
    assert prices["A2"].value == "Sol Ring"
    assert prices["B2"].value == 2
    assert prices["C2"].value == 2.0
    assert prices["C2"].number_format == '"$"#,##0.00'
    assert prices["C2"].hyperlink.target == "https://store.example/sol-ring"
    assert prices["D2"].value == "OUT_OF_STOCK"
    assert prices["E2"].value == "Don't buy"

    validations = list(prices.data_validations.dataValidation)
    assert len(validations) == 1
    assert "Don't buy" in validations[0].formula1
    assert "Wizard Tower" in validations[0].formula1
    assert "E2" in str(validations[0].sqref)

    shopping = workbook["Shopping Lists"]
    assert [cell.value for cell in shopping[1]] == [
        "Store",
        "Qty",
        "Card",
        "Unit price",
        "Line total",
    ]
    assert shopping["C2"].value == "No FOUND picks yet."


def test_write_results_xlsx_static_shopping_lists_from_picks(tmp_path: Path) -> None:
    sol_ring = _card("Sol Ring", quantity=2)
    arcane = _card("Arcane Signet")
    stores = [
        ExportStore(store_id="wizardtower", display_name="Wizard Tower"),
        ExportStore(store_id="facetoface", display_name="Face to Face"),
    ]
    results = {
        "Sol Ring": {
            "wizardtower": _result(sol_ring, "wizardtower", price="2.00"),
            "facetoface": _result(sol_ring, "facetoface", price="3.00"),
        },
        "Arcane Signet": {
            "wizardtower": _result(
                arcane,
                "wizardtower",
                status=ResultStatus.NOT_FOUND,
                price=None,
                product_url=None,
            ),
            "facetoface": _result(arcane, "facetoface", price="1.25"),
        },
    }
    picks = {
        "Sol Ring": "wizardtower",
        "Arcane Signet": "facetoface",
    }
    output_path = tmp_path / "with-picks.xlsx"

    write_results_xlsx(output_path, [sol_ring, arcane], stores, results, picks=picks)

    workbook = load_workbook(output_path)
    prices = workbook["Prices"]
    assert prices["E2"].value == "Wizard Tower"
    assert prices["E3"].value == "Face to Face"

    shopping = workbook["Shopping Lists"]
    assert shopping["A2"].value == "Wizard Tower"
    assert shopping["B2"].value == 2
    assert shopping["C2"].value == "Sol Ring"
    assert shopping["D2"].value == 2.0
    assert shopping["E2"].value == 4.0
    assert shopping["C3"].value == "Subtotal"
    assert shopping["E3"].value == 4.0

    assert shopping["A5"].value == "Face to Face"
    assert shopping["B5"].value == 1
    assert shopping["C5"].value == "Arcane Signet"
    assert shopping["D5"].value == 1.25
    assert shopping["E5"].value == 1.25
    assert shopping["C6"].value == "Subtotal"
    assert shopping["E6"].value == 1.25


def test_price_results_from_job_payload_round_trip() -> None:
    sol_ring = _card("Sol Ring", quantity=3)
    payload = {
        "stores": [{"store_id": "wizardtower", "display_name": "Wizard Tower"}],
        "cards": [
            {
                "card_name": "Sol Ring",
                "quantity": 3,
                "stores": [
                    {
                        "store_id": "wizardtower",
                        "status": "FOUND",
                        "price_cad": "2.50",
                        "product_url": "https://example.com/sol-ring",
                        "notes": "Checked 1 product listings.",
                    }
                ],
            }
        ],
    }

    stores, results = price_results_from_job_payload(payload, [sol_ring])

    assert stores == [ExportStore(store_id="wizardtower", display_name="Wizard Tower")]
    quote = results["Sol Ring"]["wizardtower"]
    assert quote.status == ResultStatus.FOUND
    assert quote.lowest_nm_price_cad == Decimal("2.50")
    assert quote.product_url == "https://example.com/sol-ring"
    assert quote.notes == "Checked 1 product listings."
