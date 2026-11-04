import argparse
from pathlib import Path

from mtg_price_checker.cli import build_cli_run_options


def _args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "bulk": False,
        "parallel_stores": False,
        "no_parallel_stores": False,
        "request_delay_seconds": None,
        "max_products_per_card": None,
        "cache_ttl_hours": 24.0,
        "no_cache": False,
        "cookies_file": None,
        "use_browser": False,
        "browser_headed": False,
        "browser_only": False,
        "browser_manual_cf": False,
        "browser_cdp_url": None,
        "browser_ui_post": False,
        "no_browser_ui_post": False,
        "browser_profile_dir": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_build_cli_run_options_defaults_to_accurate_mode() -> None:
    store_options, parallel_stores, show_progress = build_cli_run_options(_args(), card_count=5)

    assert store_options.request_delay_seconds == 8.0
    assert store_options.max_products_per_card is None
    assert parallel_stores is False
    assert show_progress is False


def test_build_cli_run_options_bulk_preset() -> None:
    store_options, parallel_stores, show_progress = build_cli_run_options(
        _args(bulk=True), card_count=50
    )

    assert store_options.request_delay_seconds == 2.0
    assert store_options.max_products_per_card == 8
    assert parallel_stores is True
    assert show_progress is True


def test_build_cli_run_options_bulk_allows_explicit_overrides() -> None:
    store_options, parallel_stores, _ = build_cli_run_options(
        _args(
            bulk=True,
            request_delay_seconds=5.0,
            max_products_per_card=3,
        ),
        card_count=10,
    )

    assert store_options.request_delay_seconds == 5.0
    assert store_options.max_products_per_card == 3
    assert parallel_stores is True


def test_build_cli_run_options_parallel_stores_without_bulk() -> None:
    _, parallel_stores, _ = build_cli_run_options(_args(parallel_stores=True), card_count=10)

    assert parallel_stores is True


def test_build_cli_run_options_no_parallel_stores_overrides_bulk() -> None:
    _, parallel_stores, _ = build_cli_run_options(
        _args(bulk=True, no_parallel_stores=True),
        card_count=10,
    )

    assert parallel_stores is False


def test_build_cli_run_options_passes_cookies_file() -> None:
    cookies_file = Path("cookies.txt")
    store_options, _, _ = build_cli_run_options(_args(cookies_file=cookies_file), card_count=1)

    assert store_options.cookies_file == cookies_file


def test_build_cli_run_options_browser_headed() -> None:
    store_options, _, _ = build_cli_run_options(_args(browser_headed=True), card_count=1)

    assert store_options.browser_headless is False
