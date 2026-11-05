from mtg_price_checker.input.decklist_parser import parse_card_line, parse_decklist_text


def test_parse_decklist_text() -> None:
    cards = parse_decklist_text("2 Sol Ring\n# skip\nArcane Signet\n")

    assert [card.normalized_name for card in cards] == ["Sol Ring", "Arcane Signet"]
    assert cards[0].quantity == 2


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


def test_parse_card_line_removes_bom_character() -> None:
    card = parse_card_line("\ufeffSol Ring")

    assert card is not None
    assert card.normalized_name == "Sol Ring"
