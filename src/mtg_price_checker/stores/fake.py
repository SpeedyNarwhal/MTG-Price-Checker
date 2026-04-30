from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.domain.store_quote import StoreQuote
from mtg_price_checker.stores.base import StoreAdapter


class FakeStoreAdapter(StoreAdapter):
    def __init__(
        self, store_id: str, display_name: str, quotes: dict[str, list[StoreQuote]]
    ) -> None:
        self._store_id = store_id
        self._display_name = display_name
        self._quotes = quotes

    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def display_name(self) -> str:
        return self._display_name

    def search_card(self, requested_card: RequestedCard) -> list[StoreQuote]:
        return self._quotes.get(requested_card.normalized_name.lower(), [])


def build_demo_stores() -> list[StoreAdapter]:
    return [
        FakeStoreAdapter(
            store_id="facetoface",
            display_name="Face to Face",
            quotes={
                "sol ring": [
                    StoreQuote(
                        store_id="facetoface",
                        requested_card_name="Sol Ring",
                        matched_card_name="Sol Ring",
                        condition=CardCondition.NEAR_MINT,
                        finish=Finish.NONFOIL,
                        price_cad=Decimal("1.49"),
                        in_stock=True,
                        product_url="https://example.com/facetoface/sol-ring",
                    )
                ],
                "arcane signet": [
                    StoreQuote(
                        store_id="facetoface",
                        requested_card_name="Arcane Signet",
                        matched_card_name="Arcane Signet",
                        condition=CardCondition.NEAR_MINT,
                        finish=Finish.NONFOIL,
                        price_cad=Decimal("0.99"),
                        in_stock=True,
                        product_url="https://example.com/facetoface/arcane-signet",
                    )
                ],
            },
        ),
        FakeStoreAdapter(
            store_id="danireon",
            display_name="Danireon",
            quotes={
                "sol ring": [
                    StoreQuote(
                        store_id="danireon",
                        requested_card_name="Sol Ring",
                        matched_card_name="Sol Ring",
                        condition=CardCondition.NEAR_MINT,
                        finish=Finish.NONFOIL,
                        price_cad=Decimal("1.39"),
                        in_stock=True,
                        product_url="https://example.com/danireon/sol-ring",
                    ),
                    StoreQuote(
                        store_id="danireon",
                        requested_card_name="Sol Ring",
                        matched_card_name="Sol Ring",
                        condition=CardCondition.LIGHTLY_PLAYED,
                        finish=Finish.NONFOIL,
                        price_cad=Decimal("0.99"),
                        in_stock=True,
                        product_url="https://example.com/danireon/sol-ring-lp",
                    ),
                ],
                "arcane signet": [
                    StoreQuote(
                        store_id="danireon",
                        requested_card_name="Arcane Signet",
                        matched_card_name="Arcane Signet",
                        condition=CardCondition.NEAR_MINT,
                        finish=Finish.NONFOIL,
                        price_cad=Decimal("1.10"),
                        in_stock=False,
                        product_url="https://example.com/danireon/arcane-signet",
                    )
                ],
            },
        ),
    ]
