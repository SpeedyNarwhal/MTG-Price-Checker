from mtg_price_checker.stores.base import StoreAdapter
from mtg_price_checker.stores.danireon import DanireonStoreAdapter
from mtg_price_checker.stores.fake import build_demo_stores
from mtg_price_checker.stores.silvergoblin import SilverGoblinStoreAdapter


def build_stores(store_ids: list[str]) -> list[StoreAdapter]:
    stores: list[StoreAdapter] = []

    for store_id in store_ids:
        normalized_store_id = store_id.strip().lower()

        if normalized_store_id == "demo":
            stores.extend(build_demo_stores())
        elif normalized_store_id == "danireon":
            stores.append(DanireonStoreAdapter())
        elif normalized_store_id in {"silvergoblin", "silver-goblin", "silver_goblin"}:
            stores.append(SilverGoblinStoreAdapter())
        else:
            raise ValueError(f"Unsupported store: {store_id}")

    return stores
