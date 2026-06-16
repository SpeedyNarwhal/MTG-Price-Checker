from mtg_price_checker.stores.shopify_common import (
    extract_product_urls_from_suggest_json,
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
