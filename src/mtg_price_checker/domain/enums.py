from enum import StrEnum


class CardCondition(StrEnum):
    NEAR_MINT = "NM"
    LIGHTLY_PLAYED = "LP"
    MODERATELY_PLAYED = "MP"
    HEAVILY_PLAYED = "HP"
    DAMAGED = "DMG"


class Finish(StrEnum):
    NONFOIL = "nonfoil"
    FOIL = "foil"
    EITHER = "either"


class ResultStatus(StrEnum):
    FOUND = "FOUND"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    ERROR = "ERROR"
