from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote


class StoreAdapter(ABC):
    @property
    @abstractmethod
    def store_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        raise NotImplementedError

    @property
    def last_listings_checked(self) -> int:
        return 0


@runtime_checkable
class BatchStoreAdapter(Protocol):
    def preload_cards(self, requested_cards: list[RequestedCard]) -> None:
        raise NotImplementedError
