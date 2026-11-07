/// <reference types="vite/client" />

type DesktopExcelExportResult =
  | { ok: true; path: string }
  | { ok: false; cancelled?: boolean; error?: string };

interface DesktopBridgeApi {
  save_excel_export(
    jobId: string,
    picks: Record<string, string>,
  ): Promise<DesktopExcelExportResult> | DesktopExcelExportResult;
}

interface Window {
  pywebview?: {
    api?: DesktopBridgeApi;
  };
}
