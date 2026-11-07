from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.price_result import PriceResult


def format_price_cell(result: PriceResult) -> str:
    if result.status == ResultStatus.FOUND and result.lowest_nm_price_cad is not None:
        return f"${result.lowest_nm_price_cad:.2f}"

    if result.status == ResultStatus.ERROR and result.notes:
        return f"ERROR: {result.notes}"

    return result.status.value
