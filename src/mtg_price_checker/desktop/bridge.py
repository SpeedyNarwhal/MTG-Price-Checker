from __future__ import annotations

from pathlib import Path
from typing import Any

from mtg_price_checker.app.excel_export import (
    ExcelExportError,
    build_job_excel_bytes,
    normalize_picks,
)
from mtg_price_checker.app.jobs import job_manager


class DesktopApi:
    """JS bridge for the pywebview desktop shell."""

    def __init__(self) -> None:
        self._window: Any | None = None

    def set_window(self, window: Any) -> None:
        self._window = window

    def save_excel_export(self, job_id: str, picks: Any = None) -> dict[str, Any]:
        job = job_manager.get_job(str(job_id))
        if job is None:
            return {"ok": False, "error": "Job not found."}

        try:
            content = build_job_excel_bytes(job, normalize_picks(picks))
        except ExcelExportError as exc:
            return {"ok": False, "error": str(exc)}

        if self._window is None:
            return {"ok": False, "error": "Desktop window is not ready."}

        import webview

        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename="mtg-prices.xlsx",
            file_types=("Excel Workbook (*.xlsx)",),
        )
        if not selected:
            return {"ok": False, "cancelled": True}

        output_path = Path(selected[0])
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")

        output_path.write_bytes(content)
        return {"ok": True, "path": str(output_path)}
