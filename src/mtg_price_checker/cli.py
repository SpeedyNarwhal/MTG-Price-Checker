import argparse
from pathlib import Path

from mtg_price_checker.input.decklist_parser import parse_card_file
from mtg_price_checker.output.csv_writer import write_audit_csv, write_price_matrix_csv
from mtg_price_checker.services.price_checker import check_prices
from mtg_price_checker.services.store_registry import StoreBuildOptions, build_stores

_DEFAULT_REQUEST_DELAY_SECONDS = 8.0
_BULK_REQUEST_DELAY_SECONDS = 2.0
_BULK_MAX_PRODUCTS_PER_CARD = 8


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mtg-prices",
        description="Check MTG card prices across supported stores.",
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="Text file containing one MTG card per line, optionally prefixed by quantity.",
    )

    parser.add_argument(
        "--stores",
        nargs="+",
        default=["danireon"],
        help="Stores to check. Supported: danireon, silvergoblin, facetoface, f2f, demo.",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/prices.csv"),
        help="CSV output path.",
    )

    parser.add_argument(
        "--audit",
        type=Path,
        default=None,
        help="Optional audit CSV output path with one row per card/store result.",
    )

    parser.add_argument(
        "--max-products-per-card",
        type=_positive_int,
        default=None,
        help=(
            "Maximum number of product detail pages to fetch per card after search discovery. "
            "Defaults: Danireon=12, Silver Goblin=12, Face to Face HTML fallback=5. "
            "Bulk mode default: 8."
        ),
    )

    parser.add_argument(
        "--request-delay-seconds",
        type=_non_negative_float,
        default=None,
        help=(
            "Minimum delay between live HTTP requests. "
            f"Default: {_DEFAULT_REQUEST_DELAY_SECONDS}. "
            f"Bulk mode default: {_BULK_REQUEST_DELAY_SECONDS}."
        ),
    )

    parser.add_argument(
        "--cache-ttl-hours",
        type=_non_negative_float,
        default=24.0,
        help="How long cached HTTP responses stay valid. Default: 24.",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable HTTP cache reads/writes for this run.",
    )

    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help="Optional Netscape-format cookies file exported from a browser session.",
    )

    parser.add_argument(
        "--use-browser",
        action="store_true",
        help=(
            "Use Playwright for Danireon and Silver Goblin requests. "
            "Install with: pip install mtg-price-checker[browser]"
        ),
    )

    parser.add_argument(
        "--bulk",
        action="store_true",
        help=(
            "Fast mode for large lists: 2s request delay, 8 product pages per card, "
            "and parallel store queries."
        ),
    )

    parser.add_argument(
        "--parallel-stores",
        action="store_true",
        help="Query all stores in parallel for each card (also enabled by --bulk).",
    )

    parser.add_argument(
        "--no-parallel-stores",
        action="store_true",
        help="Force sequential store queries even when --bulk is set.",
    )

    args = parser.parse_args()

    requested_cards = parse_card_file(args.input_file)
    store_options, parallel_stores, show_progress = build_cli_run_options(
        args, len(requested_cards)
    )

    stores = build_stores(args.stores, options=store_options)
    results = check_prices(
        requested_cards,
        stores,
        parallel_stores=parallel_stores,
        show_progress=show_progress,
    )

    write_price_matrix_csv(
        output_path=args.output,
        requested_cards=requested_cards,
        stores=stores,
        results=results,
    )

    print(f"Wrote price matrix to {args.output}")

    if args.audit is not None:
        write_audit_csv(
            output_path=args.audit,
            requested_cards=requested_cards,
            stores=stores,
            results=results,
        )

        print(f"Wrote audit CSV to {args.audit}")


def build_cli_run_options(
    args: argparse.Namespace,
    card_count: int,
) -> tuple[StoreBuildOptions, bool, bool]:
    request_delay_seconds = args.request_delay_seconds
    if request_delay_seconds is None:
        request_delay_seconds = (
            _BULK_REQUEST_DELAY_SECONDS if args.bulk else _DEFAULT_REQUEST_DELAY_SECONDS
        )

    max_products_per_card = args.max_products_per_card
    if max_products_per_card is None and args.bulk:
        max_products_per_card = _BULK_MAX_PRODUCTS_PER_CARD

    parallel_stores = args.parallel_stores or args.bulk
    if args.no_parallel_stores:
        parallel_stores = False

    show_progress = card_count > 20

    store_options = StoreBuildOptions(
        max_products_per_card=max_products_per_card,
        request_delay_seconds=request_delay_seconds,
        cache_ttl_seconds=int(args.cache_ttl_hours * 60 * 60),
        use_cache=not args.no_cache,
        cookies_file=args.cookies_file,
        use_browser=args.use_browser,
    )

    return store_options, parallel_stores, show_progress


def _positive_int(value: str) -> int:
    parsed = int(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be a positive integer.")

    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be zero or greater.")

    return parsed


if __name__ == "__main__":
    main()
