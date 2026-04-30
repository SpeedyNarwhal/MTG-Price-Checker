from dataclasses import dataclass
from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish


@dataclass(frozen=True)
class StoreQuote:
    store_id: str
    requested_card_name: str
    matched_card_name: str
    condition: CardCondition
    finish: Finish
    price_cad: Decimal
    in_stock: bool
    product_url: str | None = None
    quantity_available: int | None = None
    set_name: str | None = None
    set_code: str | None = None
    collector_number: str | None = None
    raw_title: str | None = None
    confidence_score: float = 1.0
