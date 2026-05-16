from dataclasses import dataclass

from mtg_price_checker.infra.http_client import HttpClient, HttpClientConfig
from mtg_price_checker.stores.base import StoreAdapter
from mtg_price_checker.stores.danireon import DanireonStoreAdapter
from mtg_price_checker.stores.facetoface import FaceToFaceStoreAdapter
from mtg_price_checker.stores.fake import build_demo_stores
from mtg_price_checker.stores.silvergoblin import SilverGoblinStoreAdapter


@dataclass(frozen=True)
class StoreBuildOptions:
    max_products_per_card: int | None = None
    request_delay_seconds: float = 8.0
    cache_ttl_seconds: int = 24 * 60 * 60
    use_cache: bool = True


def build_stores(
    store_ids: list[str],
    options: StoreBuildOptions | None = None,
) -> list[StoreAdapter]:
    options = options or StoreBuildOptions()

    http_client = HttpClient(
        HttpClientConfig(
            min_seconds_between_requests=options.request_delay_seconds,
            cache_ttl_seconds=options.cache_ttl_seconds,
            use_cache=options.use_cache,
        )
    )

    stores: list[StoreAdapter] = []

    for store_id in store_ids:
        normalized_store_id = store_id.strip().lower()

        if normalized_store_id == "demo":
            stores.extend(build_demo_stores())
        elif normalized_store_id == "danireon":
            stores.append(
                DanireonStoreAdapter(
                    http_client=http_client,
                    max_products_to_check=options.max_products_per_card or 2,
                )
            )
        elif normalized_store_id in {"silvergoblin", "silver-goblin", "silver_goblin"}:
            stores.append(
                SilverGoblinStoreAdapter(
                    http_client=http_client,
                    max_products_to_check=options.max_products_per_card or 5,
                )
            )
        elif normalized_store_id in {"facetoface", "face-to-face", "face_to_face", "f2f"}:
            stores.append(
                FaceToFaceStoreAdapter(
                    http_client=http_client,
                    max_products_to_check=options.max_products_per_card or 5,
                )
            )
        else:
            raise ValueError(f"Unsupported store: {store_id}")

    return stores
