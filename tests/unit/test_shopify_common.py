from decimal import Decimal

from mtg_price_checker.domain.enums import CardCondition, Finish
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.services.price_checker import (
    build_price_result,
    choose_lowest_nm_in_stock_quote,
)
from mtg_price_checker.stores.shopify_common import (
    card_names_match,
    extract_product_urls_from_search_html,
    extract_product_urls_from_suggest_json,
    merge_product_urls,
    parse_shopify_condition_variants,
    to_shopify_product_json_url,
)


def test_extract_product_urls_from_suggest_json() -> None:
    payload = {
        "resources": {
            "results": {
                "products": [
                    {
                        "title": "Sol Ring",
                        "url": "/products/sol-ring-223-commander-2017",
                    },
                    {
                        "title": "Arcane Signet",
                        "url": "/products/arcane-signet-237-commander-2020-non-foil",
                    },
                ]
            }
        }
    }

    urls = extract_product_urls_from_suggest_json(payload, "https://silvergoblin.cards")

    assert urls == [
        "https://silvergoblin.cards/products/sol-ring-223-commander-2017",
        "https://silvergoblin.cards/products/arcane-signet-237-commander-2020-non-foil",
    ]


def test_to_shopify_product_json_url() -> None:
    product_url = "https://www.danireon.com/products/sol-ring-tmc-059-commander"

    assert (
        to_shopify_product_json_url(product_url, "https://www.danireon.com")
        == "https://www.danireon.com/products/sol-ring-tmc-059-commander.js"
    )


def test_merge_product_urls_preserves_order_and_dedupes() -> None:
    suggest_urls = [
        "https://silvergoblin.cards/products/sol-ring-a",
        "https://silvergoblin.cards/products/sol-ring-b",
    ]
    html_urls = [
        "https://silvergoblin.cards/products/sol-ring-b",
        "https://silvergoblin.cards/products/counterspell-dmr",
    ]

    merged = merge_product_urls(suggest_urls, html_urls)

    assert merged == [
        "https://silvergoblin.cards/products/sol-ring-a",
        "https://silvergoblin.cards/products/sol-ring-b",
        "https://silvergoblin.cards/products/counterspell-dmr",
    ]


def test_extract_product_urls_from_search_html_includes_counterspell_when_suggest_omits_it() -> (
    None
):
    html = """
    <html>
      <body>
        <a href="/products/arcane-signet-30th-anniversary-promos">Arcane Signet</a>
        <a href="/products/counterspell-dmr-045-dominaria-remastered">Counterspell</a>
      </body>
    </html>
    """
    suggest_payload = {
        "resources": {
            "results": {
                "products": [
                    {
                        "title": "Arcane Signet",
                        "url": "/products/arcane-signet-30th-anniversary-promos",
                    }
                ]
            }
        }
    }

    suggest_urls = extract_product_urls_from_suggest_json(
        suggest_payload,
        "https://silvergoblin.cards",
    )
    html_urls = extract_product_urls_from_search_html(html, "https://silvergoblin.cards")
    merged = merge_product_urls(suggest_urls, html_urls)

    assert "https://silvergoblin.cards/products/counterspell-dmr-045-dominaria-remastered" in merged


def test_card_names_match_rejects_wrong_tcg_product_with_similar_title() -> None:
    assert card_names_match("Sol Ring", "Sol Ring") is True
    assert card_names_match("Sol Ring", "Pokemon Sol Ring Promo") is False


def test_parse_shopify_condition_variants_rejects_wrong_tcg_product() -> None:
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")
    product_json = {
        "title": "Pokemon Sol Ring Promo (123) - Pokemon Set",
        "variants": [
            {
                "title": "Near Mint",
                "price": 100,
                "available": True,
            }
        ],
    }

    quotes = parse_shopify_condition_variants(
        product_json,
        "https://silvergoblin.cards/products/pokemon-sol-ring-promo",
        requested_card,
        "silvergoblin",
        extract_card_name_from_title=lambda title: title.split("(", maxsplit=1)[0].strip(),
    )

    assert quotes == []


def test_parse_shopify_condition_variants_picks_cheapest_valid_mtg_quote() -> None:
    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    expensive = {
        "title": "Sol Ring (223) - Commander 2017",
        "variants": [{"title": "Near Mint", "price": 7200, "available": True}],
    }
    cheap = {
        "title": "Sol Ring (057) - Avatar",
        "variants": [{"title": "Near Mint", "price": 199, "available": True}],
    }

    expensive_quotes = parse_shopify_condition_variants(
        expensive,
        "https://silvergoblin.cards/products/sol-ring-expensive",
        requested_card,
        "silvergoblin",
        extract_card_name_from_title=lambda title: title.split("(", maxsplit=1)[0].strip(),
    )
    cheap_quotes = parse_shopify_condition_variants(
        cheap,
        "https://silvergoblin.cards/products/sol-ring-cheap",
        requested_card,
        "silvergoblin",
        extract_card_name_from_title=lambda title: title.split("(", maxsplit=1)[0].strip(),
    )

    best_quote = choose_lowest_nm_in_stock_quote(
        requested_card,
        expensive_quotes + cheap_quotes,
    )

    assert best_quote is not None
    assert best_quote.price_cad == Decimal("1.99")
    assert best_quote.product_url == "https://silvergoblin.cards/products/sol-ring-cheap"


def test_build_price_result_includes_listings_checked_note() -> None:
    from mtg_price_checker.domain.store_quote import StoreQuote

    requested_card = RequestedCard(input_name="Sol Ring", normalized_name="Sol Ring")

    result = build_price_result(
        requested_card,
        "danireon",
        [
            StoreQuote(
                store_id="danireon",
                requested_card_name="Sol Ring",
                matched_card_name="Sol Ring",
                condition=CardCondition.NEAR_MINT,
                finish=Finish.NONFOIL,
                price_cad=Decimal("1.99"),
                in_stock=True,
                product_url="https://example.test/products/sol-ring",
            )
        ],
        listings_checked=12,
    )

    assert result.notes == "Checked 12 product listings."
