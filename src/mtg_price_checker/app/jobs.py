from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from queue import Empty, Queue
from typing import Any

from mtg_price_checker.app.imaginaire_chrome import (
    ChromeSession,
    close_managed_chrome,
    default_cdp_url,
    ensure_chrome_for_imaginaire,
)
from mtg_price_checker.app.serialize import serialize_job_results, serialize_progress_event
from mtg_price_checker.domain.conditions import parse_min_condition_arg
from mtg_price_checker.domain.progress import ProgressEvent
from mtg_price_checker.domain.requested_card import RequestedCard
from mtg_price_checker.input.decklist_parser import parse_decklist_text
from mtg_price_checker.services.price_checker import check_prices
from mtg_price_checker.services.store_registry import (
    StoreBuildOptions,
    build_stores,
    close_store_http_clients,
)

_IMAGINAIRE_IDS = {"imaginaire", "imaginaire-en", "imaginaire-fr"}


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class Job:
    job_id: str
    status: JobStatus
    stores: list[str]
    min_condition: str
    decklist: str
    browser_cdp_url: str | None
    created_at: str
    message: str = "Queued"
    card_index: int = 0
    total_cards: int = 0
    error: str | None = None
    results: dict[str, Any] | None = None
    cancel_requested: bool = False
    events: Queue[dict[str, Any]] = field(default_factory=Queue)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._active_job_id: str | None = None

    def create_job(
        self,
        *,
        stores: list[str],
        min_condition: str,
        decklist: str,
        browser_cdp_url: str | None = None,
    ) -> Job:
        if not stores:
            raise ValueError("Select at least one store.")

        cards = parse_decklist_text(decklist)
        if not cards:
            raise ValueError("Decklist is empty.")

        parse_min_condition_arg(min_condition)

        needs_imaginaire = any(store.strip().lower() in _IMAGINAIRE_IDS for store in stores)
        resolved_cdp = browser_cdp_url or (default_cdp_url() if needs_imaginaire else None)

        with self._lock:
            if self._active_job_id is not None:
                active = self._jobs.get(self._active_job_id)
                if active is not None and active.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                    raise RuntimeError("A price check is already running.")

            job = Job(
                job_id=str(uuid.uuid4()),
                status=JobStatus.QUEUED,
                stores=stores,
                min_condition=min_condition,
                decklist=decklist,
                browser_cdp_url=resolved_cdp,
                created_at=datetime.now(UTC).isoformat(),
                total_cards=len(cards),
                message="Starting…",
            )
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id

        thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
        thread.start()
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def request_cancel(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.cancel_requested = True
            job.message = "Cancel requested…"
            return job

    def iter_events(self, job_id: str, timeout_seconds: float = 1.0):
        job = self.get_job(job_id)
        if job is None:
            return

        while True:
            try:
                event = job.events.get(timeout=timeout_seconds)
            except Empty:
                current = self.get_job(job_id)
                if current is None:
                    return
                if current.status in {
                    JobStatus.COMPLETED,
                    JobStatus.CANCELLED,
                    JobStatus.ERROR,
                }:
                    # Drain any remaining events then stop.
                    while True:
                        try:
                            yield job.events.get_nowait()
                        except Empty:
                            return
                yield {"type": "heartbeat", "status": current.status.value}
                continue

            yield event
            if event.get("type") in {"done", "error", "cancelled"}:
                return

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return

        stores = []
        chrome_session: ChromeSession | None = None
        try:
            job.status = JobStatus.RUNNING
            job.message = "Building store clients…"
            self._emit(
                job,
                {
                    "type": "status",
                    "status": job.status.value,
                    "message": job.message,
                },
            )

            requested_cards = [
                RequestedCard(
                    input_name=card.input_name,
                    normalized_name=card.normalized_name,
                    quantity=card.quantity,
                    min_condition=parse_min_condition_arg(job.min_condition),
                )
                for card in parse_decklist_text(job.decklist)
            ]
            job.total_cards = len(requested_cards)

            needs_imaginaire = any(store.strip().lower() in _IMAGINAIRE_IDS for store in job.stores)
            if needs_imaginaire:
                job.message = "Launching Chrome for Imaginaire…"
                self._emit(
                    job,
                    {
                        "type": "status",
                        "status": job.status.value,
                        "message": job.message,
                    },
                )
                chrome_session = ensure_chrome_for_imaginaire(cdp_url=job.browser_cdp_url)
                job.browser_cdp_url = chrome_session.cdp_url
                if chrome_session.launched_by_app:
                    job.message = (
                        "Chrome ready — solve Cloudflare in the Chrome window if prompted…"
                    )
                else:
                    job.message = "Using existing Chrome CDP session…"
                self._emit(
                    job,
                    {
                        "type": "status",
                        "status": job.status.value,
                        "message": job.message,
                    },
                )

            options = StoreBuildOptions(
                request_delay_seconds=2.0,
                max_products_per_card=8,
                browser_cdp_url=job.browser_cdp_url,
                browser_headless=job.browser_cdp_url is None,
            )
            stores = build_stores(job.stores, options=options)

            def on_progress(event: ProgressEvent) -> None:
                job.card_index = event.card_index
                job.total_cards = event.total_cards
                job.message = event.message
                self._emit(job, serialize_progress_event(event))

            results = check_prices(
                requested_cards,
                stores,
                parallel_stores=True,
                show_progress=False,
                on_progress=on_progress,
                should_cancel=lambda: job.cancel_requested,
            )

            payload = serialize_job_results(requested_cards, stores, results)
            job.results = payload

            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.message = (
                    f"Cancelled after {job.card_index}/{job.total_cards} cards."
                    if job.card_index
                    else "Cancelled."
                )
                self._emit(
                    job,
                    {
                        "type": "cancelled",
                        "status": job.status.value,
                        "message": job.message,
                        "results": payload,
                    },
                )
            else:
                job.status = JobStatus.COMPLETED
                job.message = f"Finished {job.total_cards} cards."
                job.card_index = job.total_cards
                self._emit(
                    job,
                    {
                        "type": "done",
                        "status": job.status.value,
                        "message": job.message,
                        "results": payload,
                    },
                )
        except Exception as exc:
            job.status = JobStatus.ERROR
            job.error = str(exc)
            job.message = f"Error: {exc}"
            self._emit(
                job,
                {
                    "type": "error",
                    "status": job.status.value,
                    "message": job.message,
                    "error": job.error,
                },
            )
        finally:
            close_store_http_clients(stores)
            if chrome_session is not None and chrome_session.launched_by_app:
                close_managed_chrome()
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None

    def _emit(self, job: Job, event: dict[str, Any]) -> None:
        job.events.put(event)


job_manager = JobManager()
