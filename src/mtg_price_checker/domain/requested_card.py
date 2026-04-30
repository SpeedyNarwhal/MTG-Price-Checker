from dataclasses import dataclass

from mtg_price_checker.domain.enums import Finish


@dataclass(frozen=True)
class RequestedCard:
    input_name: str
    normalized_name: str
    quantity: int = 1
    set_code: str | None = None
    collector_number: str | None = None
    finish_preference: Finish = Finish.EITHER
    language: str = "English"
