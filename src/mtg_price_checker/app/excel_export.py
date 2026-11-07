from __future__ import annotations

from typing import Any, Mapping

from mtg_price_checker.app.jobs import Job, JobStatus
from mtg_price_checker.domain.conditions import parse_min_condition_arg
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.input.decklist_parser import parse_decklist_text
from mtg_price_checker.output.xlsx_writer import (
    price_results_from_job_payload,
    results_xlsx_bytes,
)


class ExcelExportError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def build_job_excel_bytes(
    job: Job,
    picks: Mapping[str, str] | None = None,
) -> bytes:
    if job.status not in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
        raise ExcelExportError("Job results are not ready yet.", status_code=409)
    if job.results is None:
        raise ExcelExportError("Job has no results to export.", status_code=409)

    requested_cards = [
        RequestedCard(
            input_name=card.input_name,
            normalized_name=card.normalized_name,
            quantity=card.quantity,
            min_condition=parse_min_condition_arg(job.min_condition),
        )
        for card in parse_decklist_text(job.decklist)
    ]
    stores, results = price_results_from_job_payload(job.results, requested_cards)
    return results_xlsx_bytes(
        requested_cards=requested_cards,
        stores=stores,
        results=results,
        picks=dict(picks) if picks else None,
    )


def normalize_picks(raw_picks: Any) -> dict[str, str]:
    if not isinstance(raw_picks, dict):
        return {}
    picks: dict[str, str] = {}
    for key, value in raw_picks.items():
        if isinstance(key, str) and isinstance(value, str):
            picks[key] = value
    return picks
