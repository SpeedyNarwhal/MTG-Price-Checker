import re


def normalize_card_name(name: str) -> str:
    cleaned = name.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned
