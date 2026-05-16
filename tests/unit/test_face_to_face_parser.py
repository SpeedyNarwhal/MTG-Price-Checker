from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.facetoface import (
    _extract_product_urls_from_suggest_json,
    parse_face_to_face_product_page,
)


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


def test_extract_product_urls_from_suggest_json() -> None:
    payload = {
        "resources": {
            "results": {
                "products": [
                    {
                        "title": "Arcane Signet [237] [Commander 2020] [Non-Foil]",
                        "url": "/products/arcane-signet-237-commander-2020-non-foil",
                    },
                    {
                        "title": "Arcane Signet [283] [Modern Horizons 3 Commander] [Non-Foil]",
                        "url": "/products/arcane-signet-283-modern-horizons-3-commander-non-foil",
                    },
                ]
            }
        }
    }

    urls = _extract_product_urls_from_suggest_json(payload)

    assert urls == [
        "https://facetofacegames.com/products/arcane-signet-237-commander-2020-non-foil",
        "https://facetofacegames.com/products/arcane-signet-283-modern-horizons-3-commander-non-foil",
    ]
