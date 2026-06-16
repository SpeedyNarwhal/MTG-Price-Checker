from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.services.price_checker import choose_lowest_nm_in_stock_quote
from mtg_price_checker.stores.facetoface import (
    FaceToFaceStoreAdapter,
    parse_face_to_face_deck_builder_response,
    parse_face_to_face_product_page,
)


class FakeFaceToFaceHttpClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.post_json_calls: list[tuple[str, dict]] = []

    def post_json(self, url: str, payload: dict) -> dict:
        self.post_json_calls.append((url, payload))
        return self.payload

    def get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        raise AssertionError("Expected Deck Builder preload to avoid page fallback.")


def test_parse_face_to_face_product_page_with_nm_in_stock() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title"
              content="Arcane Signet [237] [Commander 2020] [Non-Foil]">
      </head>
      <body>
        <h1>Arcane Signet</h1>
        <div>
          Low stock: 6 left
          Alternate Art Qualifier: Default Art
          Set: Commander 2020
          Type Line: Artifact
          Release Date: 2020-04-17
          Finish: Non-Foil
          Collector #: 237
          NM (6)
          Regular price $1.49
          Add to cart
          PL (0)
          Regular price $1.19
          Out of stock
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
    )

    quotes = parse_face_to_face_product_page(
        html=html,
        product_url="https://facetofacegames.com/products/arcane-signet",
        requested_card=requested_card,
    )

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad == Decimal("1.49")
    assert nm_quote.in_stock is True
    assert nm_quote.quantity_available == 6
    assert nm_quote.finish == Finish.NONFOIL
    assert nm_quote.set_name == "Commander 2020"
    assert nm_quote.collector_number == "237"


def test_parse_face_to_face_product_page_with_nm_out_of_stock() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title"
              content="Sol Ring [274] [Revised Edition] [Non-Foil]">
      </head>
      <body>
        <h1>Sol Ring</h1>
        <div>
          Set: Revised Edition
          Type Line: Artifact
          Finish: Non-Foil
          Collector #: 274
          NM (0)
          Regular price $26.99
          Out of stock
          PL (2)
          Regular price $17.54
          Add to cart
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes = parse_face_to_face_product_page(
        html=html,
        product_url="https://facetofacegames.com/products/sol-ring",
        requested_card=requested_card,
    )

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad == Decimal("26.99")
    assert nm_quote.in_stock is False
    assert nm_quote.quantity_available == 0


def test_parse_face_to_face_product_page_ignores_wrong_card() -> None:
    html = """
    <html>
      <body>
        <h1>Sol Ring</h1>
        <div>
          Set: Commander
          Type Line: Artifact
          Finish: Non-Foil
          Collector #: 001
          NM (5)
          Regular price $1.99
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
    )

    quotes = parse_face_to_face_product_page(
        html=html,
        product_url="https://facetofacegames.com/products/sol-ring",
        requested_card=requested_card,
    )

    assert quotes == []


def test_parse_face_to_face_product_page_detects_foil() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title"
              content="Arcane Signet [297] [Commander Legends] [Foil]">
      </head>
      <body>
        <h1>Arcane Signet</h1>
        <div>
          Set: Commander Legends
          Type Line: Artifact
          Finish: Foil
          Collector #: 297
          NM (2)
          Regular price $4.49
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
    )

    quotes = parse_face_to_face_product_page(
        html=html,
        product_url="https://facetofacegames.com/products/arcane-signet",
        requested_card=requested_card,
    )

    assert quotes[0].finish == Finish.FOIL


def test_parse_face_to_face_product_page_treats_non_foil_title_as_nonfoil() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title"
              content="Arcane Signet [237] [Commander 2020] [Non-Foil]">
      </head>
      <body>
        <h1>Arcane Signet [237] [Commander 2020] [Non-Foil]</h1>
        <div>
          Set: Commander 2020
          Type Line: Artifact
          Collector #: 237
          NM (2)
          Regular price $1.49
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
    )

    quotes = parse_face_to_face_product_page(
        html=html,
        product_url="https://facetofacegames.com/products/arcane-signet",
        requested_card=requested_card,
    )

    assert quotes[0].finish == Finish.NONFOIL


def test_parse_face_to_face_deck_builder_response_with_nm_in_stock() -> None:
    payload = {
        "Cards": {
            "Sol Ring": [
                {
                    "_source": {
                        "General_Card_Name": "Sol Ring",
                        "handle": "sol-ring-057-commander-aetherdrift-non-foil",
                        "MTG_Set_Name": "Commander: Aetherdrift",
                        "MTG_Collector_Number": "057",
                        "MTG_Foil_Option": "Non-Foil",
                        "variants": [
                            {
                                "selectedOptions": [
                                    {"name": "Condition", "value": "NM"},
                                ],
                                "price": "1.49",
                                "inventoryQuantity": 3,
                            },
                            {
                                "selectedOptions": [
                                    {"name": "Condition", "value": "PL"},
                                ],
                                "price": "1.19",
                                "inventoryQuantity": 4,
                            },
                        ],
                    }
                }
            ]
        }
    }

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes, listings_checked = parse_face_to_face_deck_builder_response(
        payload=payload,
        requested_card=requested_card,
    )

    assert listings_checked == 1

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad == Decimal("1.49")
    assert nm_quote.in_stock is True
    assert nm_quote.quantity_available == 3
    assert nm_quote.finish == Finish.NONFOIL
    assert nm_quote.set_name == "Commander: Aetherdrift"
    assert nm_quote.collector_number == "057"
    assert (
        nm_quote.product_url
        == "https://facetofacegames.com/products/sol-ring-057-commander-aetherdrift-non-foil"
    )


def test_parse_face_to_face_deck_builder_response_parses_pl_but_checker_ignores_it() -> None:
    payload = {
        "Cards": {
            "Sol Ring": [
                {
                    "_source": {
                        "General_Card_Name": "Sol Ring",
                        "handle": "sol-ring-057-commander-aetherdrift-non-foil",
                        "MTG_Set_Name": "Commander: Aetherdrift",
                        "MTG_Collector_Number": "057",
                        "MTG_Foil_Option": "Non-Foil",
                        "variants": [
                            {
                                "selectedOptions": [
                                    {"name": "Condition", "value": "PL"},
                                ],
                                "price": "0.99",
                                "inventoryQuantity": 5,
                            }
                        ],
                    }
                }
            ]
        }
    }

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes, listings_checked = parse_face_to_face_deck_builder_response(
        payload=payload,
        requested_card=requested_card,
    )

    assert listings_checked == 1
    best_quote = choose_lowest_nm_in_stock_quote(requested_card, quotes)

    assert len(quotes) == 1
    assert quotes[0].condition == CardCondition.LIGHTLY_PLAYED
    assert best_quote is None


def test_face_to_face_preload_cards_batches_multiple_card_names() -> None:
    payload = {
        "Cards": {
            "Sol Ring": [
                {
                    "_source": {
                        "General_Card_Name": "Sol Ring",
                        "handle": "sol-ring-057-commander-aetherdrift-non-foil",
                        "MTG_Set_Name": "Commander: Aetherdrift",
                        "MTG_Collector_Number": "057",
                        "MTG_Foil_Option": "Non-Foil",
                        "variants": [
                            {
                                "selectedOptions": [{"name": "Condition", "value": "NM"}],
                                "price": "1.49",
                                "inventoryQuantity": 3,
                            }
                        ],
                    }
                }
            ],
            "Arcane Signet": [
                {
                    "_source": {
                        "General_Card_Name": "Arcane Signet",
                        "handle": "arcane-signet-237-commander-2020-non-foil",
                        "MTG_Set_Name": "Commander 2020",
                        "MTG_Collector_Number": "237",
                        "MTG_Foil_Option": "Non-Foil",
                        "variants": [
                            {
                                "selectedOptions": [{"name": "Condition", "value": "NM"}],
                                "price": "1.29",
                                "inventoryQuantity": 5,
                            }
                        ],
                    }
                }
            ],
        }
    }
    http_client = FakeFaceToFaceHttpClient(payload)
    adapter = FaceToFaceStoreAdapter(http_client=http_client)
    sol_ring = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")
    arcane_signet = RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet")

    adapter.preload_cards([sol_ring, arcane_signet])
    sol_ring_quotes = adapter.search_card(sol_ring)
    arcane_signet_quotes = adapter.search_card(arcane_signet)

    assert len(http_client.post_json_calls) == 1
    _, request_payload = http_client.post_json_calls[0]
    assert request_payload["filters"][0] == {
        "field": "Card Name",
        "values": ["Sol Ring", "Arcane Signet"],
    }

    assert sol_ring_quotes[0].store_id == "facetoface"
    assert sol_ring_quotes[0].matched_card_name == "Sol Ring"
    assert sol_ring_quotes[0].condition == CardCondition.NEAR_MINT
    assert sol_ring_quotes[0].price_cad == Decimal("1.49")
    assert sol_ring_quotes[0].in_stock is True
    assert sol_ring_quotes[0].quantity_available == 3
    assert (
        sol_ring_quotes[0].product_url
        == "https://facetofacegames.com/products/sol-ring-057-commander-aetherdrift-non-foil"
    )
    assert sol_ring_quotes[0].set_name == "Commander: Aetherdrift"
    assert sol_ring_quotes[0].collector_number == "057"
    assert sol_ring_quotes[0].finish == Finish.NONFOIL

    assert arcane_signet_quotes[0].matched_card_name == "Arcane Signet"
    assert arcane_signet_quotes[0].price_cad == Decimal("1.29")


def _deck_builder_product(handle: str, price: str) -> dict:
    return {
        "_source": {
            "General_Card_Name": "Arcane Signet",
            "handle": handle,
            "MTG_Set_Name": "Test Set",
            "MTG_Collector_Number": "001",
            "MTG_Foil_Option": "Non-Foil",
            "variants": [
                {
                    "selectedOptions": [{"name": "Condition", "value": "NM"}],
                    "price": price,
                    "inventoryQuantity": 2,
                }
            ],
        }
    }


def test_parse_face_to_face_deck_builder_parses_all_products_for_cheapest_nm() -> None:
    products = [
        _deck_builder_product(f"arcane-signet-{index}", f"{index + 1}.00") for index in range(7)
    ]
    products.append(_deck_builder_product("arcane-signet-cheapest", "0.75"))

    payload = {"Cards": {"Arcane Signet": products}}
    requested_card = RequestedCard(input_name="Arcane Signet", normalized_name="Arcane Signet")

    quotes, listings_checked = parse_face_to_face_deck_builder_response(
        payload=payload,
        requested_card=requested_card,
    )
    best_quote = choose_lowest_nm_in_stock_quote(requested_card, quotes)

    assert listings_checked == 8
    assert best_quote is not None
    assert best_quote.price_cad == Decimal("0.75")
    assert best_quote.product_url == "https://facetofacegames.com/products/arcane-signet-cheapest"
