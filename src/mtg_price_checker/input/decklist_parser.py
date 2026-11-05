import re
from pathlib import Path

from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.input.card_normalizer import normalize_card_name

_QUANTITY_PREFIX = re.compile(r"^\s*(?P<quantity>\d+)\s+(?P<name>.+?)\s*$")


def parse_card_line(line: str) -> RequestedCard | None:
    stripped = line.strip()

    if not stripped:
        return None

    if stripped.startswith("#"):
        return None

    match = _QUANTITY_PREFIX.match(stripped)

    if match:
        quantity = int(match.group("quantity"))
        name = match.group("name")
    else:
        quantity = 1
        name = stripped

    normalized_name = normalize_card_name(name)

    return RequestedCard(
        input_name=name,
        normalized_name=normalized_name,
        quantity=quantity,
    )


def parse_decklist_text(text: str) -> list[RequestedCard]:
    cards: list[RequestedCard] = []

    for line in text.splitlines():
        card = parse_card_line(line)
        if card is not None:
            cards.append(card)

    return cards


def parse_card_file(path: Path) -> list[RequestedCard]:
    return parse_decklist_text(_read_text_file(path))


def _read_text_file(path: Path) -> str:
    encodings_to_try = ["utf-8-sig", "utf-8", "utf-16"]

    for encoding in encodings_to_try:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError(
        "utf-8",
        b"",
        0,
        1,
        f"Could not read {path} as one of: {', '.join(encodings_to_try)}",
    )
