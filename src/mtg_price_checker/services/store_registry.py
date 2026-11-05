from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtg_price_checker.infra.browser_http_client import BrowserHttpClient
from mtg_price_checker.infra.http_client import HttpClient, HttpClientConfig
from mtg_price_checker.infra.imaginaire_http_client import ImaginaireHttpClient
from mtg_price_checker.stores.base import StoreAdapter
from mtg_price_checker.stores.danireon import DanireonStoreAdapter
from mtg_price_checker.stores.facetoface import FaceToFaceStoreAdapter
from mtg_price_checker.stores.fake import build_demo_stores
from mtg_price_checker.stores.hobbiesville import HobbiesvilleStoreAdapter
from mtg_price_checker.stores.imaginaire import ImaginaireStoreAdapter
from mtg_price_checker.stores.silvergoblin import SilverGoblinStoreAdapter
from mtg_price_checker.stores.wizardtower import WizardTowerStoreAdapter

_IMAGINAIRE_WARMUP_URL = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"
_DEFAULT_IMAGINAIRE_PROFILE_DIR = Path(".cache/browser/imaginaire")


@dataclass(frozen=True)
class StoreBuildOptions:
    max_products_per_card: int | None = None
    request_delay_seconds: float = 8.0
    cache_ttl_seconds: int = 24 * 60 * 60
    use_cache: bool = True
    cookies_file: Path | None = None
    use_browser: bool = False
    browser_headless: bool = True
    browser_only: bool = False
    browser_manual_cf: bool = False
    browser_cdp_url: str | None = None
    browser_ui_post: bool | None = None
    browser_human_delays: bool = True
    browser_profile_dir: Path | None = None


def build_stores(
    store_ids: list[str],
    options: StoreBuildOptions | None = None,
) -> list[StoreAdapter]:
    options = options or StoreBuildOptions()

    stores: list[StoreAdapter] = []

    for store_id in store_ids:
        normalized_store_id = store_id.strip().lower()

        if normalized_store_id == "demo":
            stores.extend(build_demo_stores())
        elif normalized_store_id == "danireon":
            stores.append(
                DanireonStoreAdapter(
                    http_client=_build_http_client(options, use_browser=options.use_browser),
                    max_products_to_check=options.max_products_per_card or 12,
                )
            )
        elif normalized_store_id in {"silvergoblin", "silver-goblin", "silver_goblin"}:
            stores.append(
                SilverGoblinStoreAdapter(
                    http_client=_build_http_client(options, use_browser=options.use_browser),
                    max_products_to_check=options.max_products_per_card or 12,
                )
            )
        elif normalized_store_id in {"hobbiesville", "hobbies-ville", "hobbies_ville"}:
            stores.append(
                HobbiesvilleStoreAdapter(
                    http_client=_build_http_client(options, use_browser=options.use_browser),
                    max_products_to_check=options.max_products_per_card or 12,
                )
            )
        elif normalized_store_id in {"facetoface", "face-to-face", "face_to_face", "f2f"}:
            stores.append(
                FaceToFaceStoreAdapter(
                    http_client=_build_http_client(options, use_browser=False),
                    max_products_to_check=options.max_products_per_card or 5,
                )
            )
        elif normalized_store_id in {"wizardtower", "wizard-tower", "wizard_tower", "wt"}:
            stores.append(
                WizardTowerStoreAdapter(
                    http_client=_build_http_client(options, use_browser=False),
                    max_products_to_check=options.max_products_per_card or 100,
                )
            )
        elif normalized_store_id in {"imaginaire", "imaginaire-en", "imaginaire-fr"}:
            stores.append(
                ImaginaireStoreAdapter(
                    http_client=_build_imaginaire_http_client(options),
                    max_products_to_check=options.max_products_per_card or 10,
                )
            )
        else:
            raise ValueError(f"Unsupported store: {store_id}")

    return stores


def close_store_http_clients(stores: list[StoreAdapter]) -> None:
    for store in stores:
        http_client = getattr(store, "_http_client", None)
        if http_client is not None and hasattr(http_client, "close"):
            http_client.close()


def _build_http_client(options: StoreBuildOptions, *, use_browser: bool) -> Any:
    http_config = _build_http_config(options)

    if use_browser:
        return BrowserHttpClient(http_config)

    return HttpClient(http_config)


def _build_imaginaire_http_client(options: StoreBuildOptions) -> ImaginaireHttpClient:
    profile_dir = None
    if options.browser_cdp_url is None:
        profile_dir = options.browser_profile_dir or _DEFAULT_IMAGINAIRE_PROFILE_DIR
    http_config = _build_http_config(
        options,
        cloudflare_warmup_url=_IMAGINAIRE_WARMUP_URL,
        browser_profile_dir=profile_dir,
    )
    return ImaginaireHttpClient(http_config)


def _build_http_config(
    options: StoreBuildOptions,
    *,
    cloudflare_warmup_url: str | None = None,
    browser_profile_dir: Path | None = None,
) -> HttpClientConfig:
    return HttpClientConfig(
        min_seconds_between_requests=options.request_delay_seconds,
        cache_ttl_seconds=options.cache_ttl_seconds,
        use_cache=options.use_cache,
        cookies_file=options.cookies_file,
        browser_headless=options.browser_headless,
        browser_only=options.browser_only,
        browser_manual_cf=options.browser_manual_cf,
        browser_cdp_url=options.browser_cdp_url,
        browser_ui_post=options.browser_ui_post,
        browser_human_delays=options.browser_human_delays,
        browser_profile_dir=browser_profile_dir,
        cloudflare_warmup_url=cloudflare_warmup_url,
    )
