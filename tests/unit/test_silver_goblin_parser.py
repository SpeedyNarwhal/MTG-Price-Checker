from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.silvergoblin import (
    parse_silver_goblin_product_json,
    parse_silver_goblin_product_page_html,
)


def test_parse_silver_goblin_product_json_with_nm_in_stock() -> None:
    product_json = {
        "title": "Sol Ring (057) - Commander: Aetherdrift",
        "variants": [
            {
                "title": "Near Mint",
                "price": 190,
                "available": True,
            },
            {
                "title": "Lightly Played",
                "price": 170,
                "available": True,
            },
        ],
    }

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes = parse_silver_goblin_product_json(
        product_json=product_json,
        product_url="https://silvergoblin.cards/products/sol-ring",
        requested_card=requested_card,
    )

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad == Decimal("1.9")
    assert nm_quote.in_stock is True
    assert nm_quote.finish == Finish.NONFOIL
    assert nm_quote.collector_number == "057"


def test_parse_silver_goblin_product_json_with_nm_sold_out() -> None:
    product_json = {
        "title": "Blood Crypt (292) - Ravnica Remastered",
        "variants": [
            {
                "title": "Near Mint",
                "price": 2340,
                "available": False,
            }
        ],
    }

    requested_card = RequestedCard(
        input_name="Blood Crypt",
        normalized_name="Blood Crypt",
    )

    quotes = parse_silver_goblin_product_json(
        product_json=product_json,
        product_url="https://silvergoblin.cards/products/blood-crypt",
        requested_card=requested_card,
    )

    assert quotes[0].condition == CardCondition.NEAR_MINT
    assert quotes[0].price_cad == Decimal("23.4")
    assert quotes[0].in_stock is False


def test_parse_silver_goblin_product_json_ignores_wrong_card() -> None:
    product_json = {
        "title": "Arcane Signet (331) - Commander Legends",
        "variants": [
            {
                "title": "Near Mint",
                "price": 100,
                "available": True,
            }
        ],
    }

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes = parse_silver_goblin_product_json(
        product_json=product_json,
        product_url="https://silvergoblin.cards/products/arcane-signet",
        requested_card=requested_card,
    )

    assert quotes == []


def test_parse_silver_goblin_product_json_detects_foil_variant() -> None:
    product_json = {
        "title": "Fetid Pools (2520) Foil - Secret Lair Drop Series",
        "variants": [
            {
                "title": "Near Mint Foil",
                "price": 400,
                "available": True,
            }
        ],
    }

    requested_card = RequestedCard(
        input_name="Fetid Pools",
        normalized_name="Fetid Pools",
    )

    quotes = parse_silver_goblin_product_json(
        product_json=product_json,
        product_url="https://silvergoblin.cards/products/fetid-pools",
        requested_card=requested_card,
    )

    assert quotes[0].finish == Finish.FOIL


def test_parse_silver_goblin_html_fallback_with_nm_unavailable() -> None:
    html = """
    <html>
      <body>
        <h1>Sphere of Grace (049) - Odyssey</h1>
        <div>
          Regular price $0.50 CAD
          4 in stock
          Condition:
          Near Mint Variant sold out or unavailable
          Lightly Played
          Moderately Played
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Sphere of Grace",
        normalized_name="Sphere of Grace",
    )

    quotes = parse_silver_goblin_product_page_html(
        html=html,
        product_url="https://silvergoblin.cards/products/sphere-of-grace",
        requested_card=requested_card,
    )

    assert quotes[0].condition == CardCondition.NEAR_MINT
    assert quotes[0].price_cad == Decimal("0.50")
    assert quotes[0].in_stock is False


def test_parse_silver_goblin_product_json_treats_default_variant_as_nm() -> None:
    product_json = {
        "title": "Sol Ring (129) - Bloomburrow Commander",
        "variants": [
            {
                "title": "Default Title",
                "price": 150,
                "available": True,
            }
        ],
    }

    requested_card = RequestedCard(
        input_name="Sol Ring",
        normalized_name="Sol Ring",
    )

    quotes = parse_silver_goblin_product_json(
        product_json=product_json,
        product_url="https://silvergoblin.cards/products/sol-ring",
        requested_card=requested_card,
    )

    assert len(quotes) == 1
    assert quotes[0].condition == CardCondition.NEAR_MINT
    assert quotes[0].price_cad == Decimal("1.5")
    assert quotes[0].in_stock is True
