from mtg_price_checker.services.store_registry import StoreBuildOptions, build_stores


def test_build_stores_creates_separate_http_clients_per_store() -> None:
    stores = build_stores(
        ["danireon", "silvergoblin", "facetoface"],
        options=StoreBuildOptions(),
    )

    http_clients = [store._http_client for store in stores]

    assert len(http_clients) == len(set(id(client) for client in http_clients))


def test_build_stores_bulk_max_products_override() -> None:
    stores = build_stores(
        ["danireon", "silvergoblin"],
        options=StoreBuildOptions(max_products_per_card=8),
    )

    for store in stores:
        assert store._max_products_to_check == 8
