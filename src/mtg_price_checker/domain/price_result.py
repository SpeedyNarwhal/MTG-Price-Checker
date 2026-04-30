from dataclasses import dataclass
from decimal import Decimal

from mtg_price_checker.domain.enums import ResultStatus
from mtg_price_checker.domain.requested_card import RequestedCard


@dataclass(frozen=True)
class PriceResult:
    requested_card: RequestedCard
    store_id: str
    status: ResultStatus
    lowest_nm_price_cad: Decimal | None = None
    product_url: str | None = None
    notes: str | None = None
