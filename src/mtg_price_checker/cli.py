import argparse
from pathlib import Path

from mtg_price_checker.input.decklist_parser import parse_card_file
from mtg_price_checker.output.csv_writer import write_price_matrix_csv
from mtg_price_checker.services.price_checker import check_prices
from mtg_price_checker.services.store_registry import build_stores


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
        help="Stores to check. Supported: danireon, demo.",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/prices.csv"),
        help="CSV output path.",
    )

    args = parser.parse_args()

    requested_cards = parse_card_file(args.input_file)
    stores = build_stores(args.stores)
    results = check_prices(requested_cards, stores)

    write_price_matrix_csv(
        output_path=args.output,
        requested_cards=requested_cards,
        stores=stores,
        results=results,
    )

    print(f"Wrote price matrix to {args.output}")
