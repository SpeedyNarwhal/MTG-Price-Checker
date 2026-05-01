from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.danireon import parse_danireon_product_page


def test_parse_danireon_product_page_with_nm_in_stock() -> None:
    html = """
    <html>
      <body>
        <h1>Cornered by Black Mages (FIN-093) - FINAL FANTASY</h1>
        <div>
          Options Near Mint - $0.33 CAD
          Lightly Played - $0.28 CAD - sold out!
          Moderately Played - $0.23 CAD - sold out!
          Heavily Played - $0.17 CAD - sold out!
          Damaged - $0.10 CAD - sold out!
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Cornered by Black Mages",
        normalized_name="Cornered by Black Mages",
    )

    quotes = parse_danireon_product_page(
        html=html,
        product_url="https://www.danireon.com/example",
        requested_card=requested_card,
    )

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad == Decimal("0.33")
    assert nm_quote.in_stock is True
    assert nm_quote.finish == Finish.NONFOIL
    assert nm_quote.set_code == "FIN"
    assert nm_quote.collector_number == "093"


def test_parse_danireon_product_page_with_nm_sold_out() -> None:
    html = """
    <html>
      <body>
        <h1>Blood Crypt (RNA-245) - Ravnica Allegiance</h1>
        <div>
          Options Near Mint - Sold out
          Lightly Played - $11.96 CAD
          Moderately Played - Sold out
          Heavily Played - Sold out
          Damaged - Sold out
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Blood Crypt",
        normalized_name="Blood Crypt",
    )

    quotes = parse_danireon_product_page(
        html=html,
        product_url="https://www.danireon.com/example",
        requested_card=requested_card,
    )

    nm_quote = next(quote for quote in quotes if quote.condition == CardCondition.NEAR_MINT)

    assert nm_quote.price_cad is None
    assert nm_quote.in_stock is False


def test_parse_danireon_product_page_ignores_wrong_card() -> None:
    html = """
    <html>
      <body>
        <h1>Sol Ring (LTC-300) - Commander</h1>
        <div>
          Options Near Mint - $1.99 CAD
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Arcane Signet",
        normalized_name="Arcane Signet",
    )

    quotes = parse_danireon_product_page(
        html=html,
        product_url="https://www.danireon.com/example",
        requested_card=requested_card,
    )

    assert quotes == []


def test_parse_danireon_product_page_detects_foil() -> None:
    html = """
    <html>
      <body>
        <h1>Locke Cole (FIN-234) - FINAL FANTASY Foil</h1>
        <div>
          Options Near Mint - $0.42 CAD
        </div>
      </body>
    </html>
    """

    requested_card = RequestedCard(
        input_name="Locke Cole",
        normalized_name="Locke Cole",
    )

    quotes = parse_danireon_product_page(
        html=html,
        product_url="https://www.danireon.com/example",
        requested_card=requested_card,
    )

    assert quotes[0].finish == Finish.FOIL
