from __future__ import annotations

import re

from mtg_price_checker.domain.enums import CardCondition

# Best (0) → worst. Lower rank number = better condition.
_CONDITION_RANK: dict[CardCondition, int] = {
    CardCondition.NEAR_MINT: 0,
    CardCondition.LIGHTLY_PLAYED: 1,
    CardCondition.MODERATELY_PLAYED: 2,
    CardCondition.HEAVILY_PLAYED: 3,
    CardCondition.DAMAGED: 4,
}

# Store / CLI aliases → canonical CardCondition (keys are space-normalized lowercase).
_CONDITION_ALIASES: dict[str, CardCondition] = {
    "nm": CardCondition.NEAR_MINT,
    "near mint": CardCondition.NEAR_MINT,
    "lp": CardCondition.LIGHTLY_PLAYED,
    "pl": CardCondition.LIGHTLY_PLAYED,  # Face to Face
    "sp": CardCondition.LIGHTLY_PLAYED,  # Imaginaire Slightly Played
    "lightly played": CardCondition.LIGHTLY_PLAYED,
    "slightly played": CardCondition.LIGHTLY_PLAYED,
    "mp": CardCondition.MODERATELY_PLAYED,
    "moderately played": CardCondition.MODERATELY_PLAYED,
    "hp": CardCondition.HEAVILY_PLAYED,
    "heavily played": CardCondition.HEAVILY_PLAYED,
    "dmg": CardCondition.DAMAGED,
    "dm": CardCondition.DAMAGED,
    "damaged": CardCondition.DAMAGED,
}


def _normalize_condition_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", " ", value.strip().lower()).strip()


def condition_rank(condition: CardCondition) -> int:
    return _CONDITION_RANK[condition]


def condition_meets_minimum(
    condition: CardCondition,
    minimum: CardCondition,
) -> bool:
    """True when `condition` is at least as good as `minimum` (e.g. NM meets LP)."""
    return condition_rank(condition) <= condition_rank(minimum)


def parse_condition_label(value: str) -> CardCondition | None:
    return _CONDITION_ALIASES.get(_normalize_condition_key(value))


def parse_min_condition_arg(value: str) -> CardCondition:
    parsed = parse_condition_label(value)
    if parsed is None:
        allowed = "NM, LP/SP/PL, MP, HP, DMG"
        raise ValueError(f"Unknown condition {value!r}. Use one of: {allowed}.")
    return parsed
