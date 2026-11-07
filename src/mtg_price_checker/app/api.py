from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mtg_price_checker.app.excel_export import ExcelExportError, build_job_excel_bytes
from mtg_price_checker.app.imaginaire_chrome import (
    cdp_status,
    default_cdp_url,
    launch_chrome_for_imaginaire,
)
from mtg_price_checker.app.jobs import JobStatus, job_manager
from mtg_price_checker.paths import frontend_dist_dir

_STATIC_DIR = frontend_dist_dir()


class CreateJobRequest(BaseModel):
    stores: list[str] = Field(min_length=1)
    min_condition: str = "NM"
    decklist: str
    browser_cdp_url: str | None = None


class LaunchChromeRequest(BaseModel):
    cdp_port: int = 9222
    open_deck_builder: bool = True


class ExportExcelRequest(BaseModel):
    picks: dict[str, str] = Field(default_factory=dict)


def create_app() -> FastAPI:
    app = FastAPI(title="MTG Price Checker", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/stores")
    def list_stores() -> dict[str, Any]:
        return {
            "stores": [
                {"store_id": "danireon", "display_name": "Danireon"},
                {"store_id": "silvergoblin", "display_name": "Silver Goblin"},
                {"store_id": "facetoface", "display_name": "Face to Face"},
                {"store_id": "hobbiesville", "display_name": "Hobbiesville"},
                {"store_id": "wizardtower", "display_name": "Wizard Tower"},
                {"store_id": "imaginaire", "display_name": "Imaginaire", "requires_cdp": True},
            ],
            "default_cdp_url": default_cdp_url(),
        }

    @app.get("/api/imaginaire/cdp-status")
    def imaginaire_cdp_status(cdp_url: str | None = None) -> dict[str, Any]:
        return cdp_status(cdp_url or default_cdp_url())

    @app.post("/api/imaginaire/launch-chrome")
    def imaginaire_launch_chrome(body: LaunchChromeRequest | None = None) -> dict[str, Any]:
        request = body or LaunchChromeRequest()
        try:
            return launch_chrome_for_imaginaire(
                cdp_port=request.cdp_port,
                open_deck_builder=request.open_deck_builder,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/jobs")
    def create_job(body: CreateJobRequest) -> dict[str, Any]:
        try:
            job = job_manager.create_job(
                stores=body.stores,
                min_condition=body.min_condition,
                decklist=body.decklist,
                browser_cdp_url=body.browser_cdp_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return _job_summary(job)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return _job_summary(job)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        job = job_manager.request_cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return _job_summary(job)

    @app.get("/api/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        def event_stream():
            for event in job_manager.iter_events(job_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/jobs/{job_id}/export.xlsx")
    def export_job_excel(job_id: str, body: ExportExcelRequest | None = None) -> Response:
        job = job_manager.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")

        request = body or ExportExcelRequest()
        try:
            content = build_job_excel_bytes(job, request.picks or None)
        except ExcelExportError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return Response(
            content=content,
            media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            headers={
                "Content-Disposition": 'attachment; filename="mtg-prices.xlsx"',
            },
        )

    if _STATIC_DIR.is_dir():
        assets_dir = _STATIC_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            candidate = _STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(_STATIC_DIR / "index.html")

    return app


def _job_summary(job: Any) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status.value if isinstance(job.status, JobStatus) else job.status,
        "message": job.message,
        "card_index": job.card_index,
        "total_cards": job.total_cards,
        "error": job.error,
        "stores": job.stores,
        "min_condition": job.min_condition,
        "browser_cdp_url": job.browser_cdp_url,
        "results": job.results,
    }


app = create_app()
