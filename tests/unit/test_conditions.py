import pytest

from mtg_price_checker.domain.conditions import (
    condition_meets_minimum,
    parse_condition_label,
    parse_min_condition_arg,
)
from mtg_price_checker.domain.enums import CardCondition


def test_condition_meets_minimum_ladder() -> None:
    assert condition_meets_minimum(CardCondition.NEAR_MINT, CardCondition.NEAR_MINT)
    assert condition_meets_minimum(CardCondition.NEAR_MINT, CardCondition.LIGHTLY_PLAYED)
    assert not condition_meets_minimum(CardCondition.LIGHTLY_PLAYED, CardCondition.NEAR_MINT)
    assert condition_meets_minimum(CardCondition.MODERATELY_PLAYED, CardCondition.HEAVILY_PLAYED)


def test_parse_condition_label_store_aliases() -> None:
    assert parse_condition_label("NM") == CardCondition.NEAR_MINT
    assert parse_condition_label("Near Mint") == CardCondition.NEAR_MINT
    assert parse_condition_label("SP") == CardCondition.LIGHTLY_PLAYED
    assert parse_condition_label("PL") == CardCondition.LIGHTLY_PLAYED
    assert parse_condition_label("Lightly Played") == CardCondition.LIGHTLY_PLAYED
    assert parse_condition_label("MP") == CardCondition.MODERATELY_PLAYED
    assert parse_condition_label("DM") == CardCondition.DAMAGED
    assert parse_condition_label("nope") is None


def test_parse_min_condition_arg() -> None:
    assert parse_min_condition_arg("lp") == CardCondition.LIGHTLY_PLAYED
    assert parse_min_condition_arg("slightly-played") == CardCondition.LIGHTLY_PLAYED
    with pytest.raises(ValueError, match="Unknown condition"):
        parse_min_condition_arg("excellent")
