from decimal import Decimal
from typing import Any

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.services.price_checker import choose_lowest_in_stock_quote
from mtg_price_checker.services.store_registry import StoreBuildOptions, build_stores
from mtg_price_checker.stores.wizardtower import (
    WizardTowerStoreAdapter,
    parse_wizard_tower_lookup_results,
)


class FakeWizardTowerHttpClient:
    def __init__(self, payloads: list[dict[str, Any]] | dict[str, Any]) -> None:
        if isinstance(payloads, dict):
            self._payloads = [payloads]
        else:
            self._payloads = payloads
        self.post_json_calls: list[tuple[str, dict[str, Any]]] = []
        self._call_index = 0

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.post_json_calls.append((url, payload))
        response = self._payloads[min(self._call_index, len(self._payloads) - 1)]
        self._call_index += 1
        return response


def _product(
    *,
    title: str = "Sol Ring",
    full_title: str = "Sol Ring (0284) (LTC)",
    url: str = "/products/sol-ring-0284-ltc",
    card_set: str = "Universes Beyond: Lord of the Rings - Commander",
    collector_number: str = "0284",
    finish_value: str = "Regular",
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "full_title": full_title,
        "url": url,
        "card_set": card_set,
        "collector_number": collector_number,
        "tags": [{"field": "mtg_mtg_finish", "value": finish_value}],
        "variants": variants
        or [
            {
                "condition_code": "NM",
                "price": 5,
                "inventory_quantity": 3,
                "available": True,
            },
            {
                "condition_code": "SP",
                "price": 4.6,
                "inventory_quantity": 1,
                "available": True,
            },
        ],
    }


def test_parse_exact_match_emits_nm_and_sp_quotes() -> None:
    payload = {
        "results": [
            {
                "cardName": "Sol Ring",
                "match": "exact",
                "products": [_product()],
            }
        ]
    }
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    quotes, listings_checked = parse_wizard_tower_lookup_results(payload, requested_card)

    assert listings_checked == 1
    assert len(quotes) == 2

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)
    sp_quote = next(quote for quote in quotes if quote.condition == CardCondition.LIGHTLY_PLAYED)

    assert nm_quote.store_id == "wizardtower"
    assert nm_quote.matched_card_name == "Sol Ring"
    assert nm_quote.price_cad == Decimal("5")
    assert nm_quote.in_stock is True
    assert nm_quote.quantity_available == 3
    assert nm_quote.product_url == "https://store.wizardtower.com/products/sol-ring-0284-ltc"
    assert nm_quote.set_name == "Universes Beyond: Lord of the Rings - Commander"
    assert nm_quote.collector_number == "0284"
    assert nm_quote.finish == Finish.NONFOIL

    assert sp_quote.price_cad == Decimal("4.6")
    assert sp_quote.in_stock is True

    best = choose_lowest_in_stock_quote(requested_card, quotes)
    assert best is not None
    assert best.condition == CardCondition.NEAR_MINT
    assert best.price_cad == Decimal("5")


def test_parse_foil_tag_and_sp_condition() -> None:
    payload = {
        "results": [
            {
                "cardName": "Arcane Signet",
                "match": "exact",
                "products": [
                    _product(
                        title="Arcane Signet",
                        full_title="Arcane Signet (0001) (Commander) (PF25) - Foil",
                        url="/products/arcane-signet-0001-commander-pf25-foil",
                        finish_value="Foil",
                        variants=[
                            {
                                "condition_code": "SP",
                                "price": 38.64,
                                "inventory_quantity": 2,
                                "available": True,
                            }
                        ],
                    )
                ],
            }
        ]
    }
    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
        min_condition=CardCondition.LIGHTLY_PLAYED,
    )

    quotes, listings_checked = parse_wizard_tower_lookup_results(payload, requested_card)

    assert listings_checked == 1
    assert len(quotes) == 1
    assert quotes[0].condition == CardCondition.LIGHTLY_PLAYED
    assert quotes[0].finish == Finish.FOIL
    assert quotes[0].price_cad == Decimal("38.64")


def test_parse_match_none_returns_empty() -> None:
    payload = {
        "results": [
            {
                "cardName": "This Card Does Not Exist XYZ",
                "match": "none",
                "products": [],
            }
        ]
    }
    requested_card = RequestedCard(
        input_name="This Card Does Not Exist XYZ",
        normalized_name="This Card Does Not Exist XYZ",
    )

    quotes, listings_checked = parse_wizard_tower_lookup_results(payload, requested_card)

    assert quotes == []
    assert listings_checked == 0


def test_preload_cards_batches_multiple_card_names() -> None:
    payload = {
        "results": [
            {
                "cardName": "Sol Ring",
                "match": "exact",
                "products": [_product()],
            },
            {
                "cardName": "Arcane Signet",
                "match": "exact",
                "products": [
                    _product(
                        title="Arcane Signet",
                        full_title="Arcane Signet (237) (C20)",
                        url="/products/arcane-signet-237-c20",
                        collector_number="237",
                        variants=[
                            {
                                "condition_code": "NM",
                                "price": 1.29,
                                "inventory_quantity": 5,
                                "available": True,
                            }
                        ],
                    )
                ],
            },
        ]
    }
    http_client = FakeWizardTowerHttpClient(payload)
    adapter = WizardTowerStoreAdapter(http_client=http_client)
    sol_ring = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")
    arcane_signet = RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet")

    adapter.preload_cards([sol_ring, arcane_signet])
    sol_ring_quotes = adapter.search_card(sol_ring)
    arcane_signet_quotes = adapter.search_card(arcane_signet)

    assert len(http_client.post_json_calls) == 1
    url, request_payload = http_client.post_json_calls[0]
    assert url.endswith("/apps/deckbuilder/lookup")
    assert request_payload == {
        "game": "magic",
        "names": ["Sol Ring", "Arcane Signet"],
    }

    assert sol_ring_quotes[0].price_cad == Decimal("5")
    assert arcane_signet_quotes[0].price_cad == Decimal("1.29")
    assert adapter.last_listings_checked == 1


def test_preload_cards_chunks_over_100_names() -> None:
    first_batch_names = [f"Card {index}" for index in range(1, 101)]
    second_batch_names = [f"Card {index}" for index in range(101, 106)]

    payloads = [
        {
            "results": [
                {
                    "cardName": name,
                    "match": "exact",
                    "products": [
                        _product(
                            title=name,
                            full_title=name,
                            url=f"/products/{name.lower().replace(' ', '-')}",
                            variants=[
                                {
                                    "condition_code": "NM",
                                    "price": 1,
                                    "inventory_quantity": 1,
                                    "available": True,
                                }
                            ],
                        )
                    ],
                }
                for name in first_batch_names
            ]
        },
        {
            "results": [
                {
                    "cardName": name,
                    "match": "exact",
                    "products": [
                        _product(
                            title=name,
                            full_title=name,
                            url=f"/products/{name.lower().replace(' ', '-')}",
                            variants=[
                                {
                                    "condition_code": "NM",
                                    "price": 2,
                                    "inventory_quantity": 1,
                                    "available": True,
                                }
                            ],
                        )
                    ],
                }
                for name in second_batch_names
            ]
        },
    ]
    http_client = FakeWizardTowerHttpClient(payloads)
    adapter = WizardTowerStoreAdapter(http_client=http_client)
    cards = [
        RequestedCard(input_name=name, normalized_name=name)
        for name in first_batch_names + second_batch_names
    ]

    adapter.preload_cards(cards)

    assert len(http_client.post_json_calls) == 2
    assert http_client.post_json_calls[0][1]["names"] == first_batch_names
    assert http_client.post_json_calls[1][1]["names"] == second_batch_names
    assert len(adapter.search_card(cards[0])) == 1
    assert adapter.search_card(cards[-1])[0].price_cad == Decimal("2")


def test_build_stores_wizardtower_aliases() -> None:
    for store_id in ("wizardtower", "wizard-tower", "wizard_tower", "wt"):
        stores = build_stores([store_id], options=StoreBuildOptions())
        assert len(stores) == 1
        assert stores[0].store_id == "wizardtower"
        assert stores[0].display_name == "Wizard Tower"
