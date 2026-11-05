from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    card_index: int
    total_cards: int
    card_name: str
    message: str
    store_statuses: dict[str, str]
