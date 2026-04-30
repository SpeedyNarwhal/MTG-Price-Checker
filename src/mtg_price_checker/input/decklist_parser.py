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


def parse_card_file(path: Path) -> list[RequestedCard]:
    cards: list[RequestedCard] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        card = parse_card_line(line)
        if card is not None:
            cards.append(card)

    return cards
