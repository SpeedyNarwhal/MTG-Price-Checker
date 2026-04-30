from mtg_price_checker.input.decklist_parser import parse_card_line


def test_parse_card_line_with_quantity() -> None:
    card = parse_card_line("2 Sol Ring")

    assert card is not None
    assert card.quantity == 2
    assert card.input_name == "Sol Ring"
    assert card.normalized_name == "Sol Ring"


def test_parse_card_line_without_quantity_defaults_to_one() -> None:
    card = parse_card_line("Arcane Signet")

    assert card is not None
    assert card.quantity == 1
    assert card.normalized_name == "Arcane Signet"


def test_parse_card_line_ignores_blank_lines() -> None:
    assert parse_card_line("") is None
    assert parse_card_line("   ") is None


def test_parse_card_line_ignores_comments() -> None:
    assert parse_card_line("# commander staples") is None
