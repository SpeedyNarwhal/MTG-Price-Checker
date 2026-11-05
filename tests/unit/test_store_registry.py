from mtg_price_checker.services.store_registry import StoreBuildOptions, build_stores


def test_build_stores_creates_separate_http_clients_per_store() -> None:
    stores = build_stores(
        ["danireon", "silvergoblin", "hobbiesville", "facetoface"],
        options=StoreBuildOptions(),
    )

    http_clients = [store._http_client for store in stores]

    assert len(http_clients) == len(set(id(client) for client in http_clients))


def test_build_stores_bulk_max_products_override() -> None:
    stores = build_stores(
        ["danireon", "silvergoblin", "hobbiesville"],
        options=StoreBuildOptions(max_products_per_card=8),
    )

    for store in stores:
        assert store._max_products_to_check == 8


def test_build_stores_hobbiesville_defaults() -> None:
    stores = build_stores(["hobbiesville"], options=StoreBuildOptions())

    assert len(stores) == 1
    assert stores[0].store_id == "hobbiesville"
    assert stores[0]._max_products_to_check == 12


def test_build_stores_wizardtower_defaults() -> None:
    stores = build_stores(["wizardtower"], options=StoreBuildOptions())

    assert len(stores) == 1
    assert stores[0].store_id == "wizardtower"
    assert stores[0]._max_products_to_check == 100
