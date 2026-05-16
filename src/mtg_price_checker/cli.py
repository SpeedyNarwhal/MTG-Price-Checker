import argparse
from pathlib import Path

from mtg_price_checker.input.decklist_parser import parse_card_file
from mtg_price_checker.output.csv_writer import write_audit_csv, write_price_matrix_csv
from mtg_price_checker.services.price_checker import check_prices
from mtg_price_checker.services.store_registry import StoreBuildOptions, build_stores


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
            "Maximum number of candidate product pages to check per card per store. "
            "Defaults: Danireon=2, Silver Goblin=5."
        ),
    )

    parser.add_argument(
        "--request-delay-seconds",
        type=_non_negative_float,
        default=8.0,
        help="Minimum delay between live HTTP requests. Default: 8.",
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

    args = parser.parse_args()

    requested_cards = parse_card_file(args.input_file)

    store_options = StoreBuildOptions(
        max_products_per_card=args.max_products_per_card,
        request_delay_seconds=args.request_delay_seconds,
        cache_ttl_seconds=int(args.cache_ttl_hours * 60 * 60),
        use_cache=not args.no_cache,
    )

    stores = build_stores(args.stores, options=store_options)
    results = check_prices(requested_cards, stores)

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
