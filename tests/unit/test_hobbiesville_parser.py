from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.stores.hobbiesville import parse_hobbiesville_product_json


def test_parse_hobbiesville_product_json_nm_in_stock() -> None:
    product_json = {
        "title": "Sol Ring (LTC-284)",
        "variants": [
            {
                "title": "NM",
                "option1": "NM",
                "price": 475,
                "available": True,
            },
            {
                "title": "LP",
                "option1": "LP",
                "price": 404,
                "available": False,
            },
            {
                "title": "MP",
                "option1": "MP",
                "price": 309,
                "available": False,
            },
        ],
    }

    quotes = parse_hobbiesville_product_json(
        product_json=product_json,
        product_url="https://www.hobbiesville.com/products/sol-ring-ltc-284",
        requested_card=RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
    )

    assert len(quotes) == 3
    nm_quote = quotes[0]
    assert nm_quote.condition == CardCondition.NEAR_MINT
    assert nm_quote.price_cad == Decimal("4.75")
    assert nm_quote.in_stock is True
    assert nm_quote.finish == Finish.NONFOIL
    assert nm_quote.set_code == "LTC"
    assert nm_quote.collector_number == "284"
    assert quotes[1].condition == CardCondition.LIGHTLY_PLAYED
    assert quotes[1].in_stock is False
    assert quotes[2].condition == CardCondition.MODERATELY_PLAYED


def test_parse_hobbiesville_product_json_detects_foil() -> None:
    product_json = {
        "title": "Sol Ring (Borderless) (SOC-427) Foil",
        "variants": [
            {
                "title": "NM",
                "option1": "NM",
                "price": 2650,
                "available": True,
            }
        ],
    }

    quotes = parse_hobbiesville_product_json(
        product_json=product_json,
        product_url="https://www.hobbiesville.com/products/sol-ring-borderless-soc-427-foil",
        requested_card=RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
    )

    assert len(quotes) == 1
    assert quotes[0].finish == Finish.FOIL
    assert quotes[0].price_cad == Decimal("26.50")
    assert quotes[0].set_code == "SOC"
    assert quotes[0].collector_number == "427"


def test_parse_hobbiesville_product_json_ignores_wrong_card() -> None:
    product_json = {
        "title": "Arcane Signet (C21-243)",
        "variants": [
            {
                "title": "NM",
                "option1": "NM",
                "price": 199,
                "available": True,
            }
        ],
    }

    quotes = parse_hobbiesville_product_json(
        product_json=product_json,
        product_url="https://www.hobbiesville.com/products/arcane-signet-c21-243",
        requested_card=RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
    )

    assert quotes == []


def test_parse_hobbiesville_product_json_out_of_stock_nm() -> None:
    product_json = {
        "title": "Sol Ring (PIP-239)",
        "variants": [
            {
                "title": "NM",
                "option1": "NM",
                "price": 300,
                "available": False,
            },
            {
                "title": "LP",
                "option1": "LP",
                "price": 255,
                "available": False,
            },
        ],
    }

    quotes = parse_hobbiesville_product_json(
        product_json=product_json,
        product_url="https://www.hobbiesville.com/products/sol-ring-pip-239",
        requested_card=RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring"),
    )

    assert len(quotes) == 2
    assert quotes[0].condition == CardCondition.NEAR_MINT
    assert quotes[0].in_stock is False
    assert quotes[0].price_cad == Decimal("3.00")
