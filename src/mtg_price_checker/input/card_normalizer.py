import re

_INVISIBLE_CHARACTERS = [
    "\ufeff",  # UTF byte order mark
    "\u200b",  # zero-width space
]


def normalize_card_name(name: str) -> str:
    cleaned = name

    for character in _INVISIBLE_CHARACTERS:
        cleaned = cleaned.replace(character, "")

    cleaned = cleaned.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned
