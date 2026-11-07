import type { JobEvent, JobSummary, StoreInfo } from "./types";

export async function fetchStores(): Promise<{
  stores: StoreInfo[];
  default_cdp_url: string;
}> {
  const response = await fetch("/api/stores");
  if (!response.ok) {
    throw new Error("Failed to load stores.");
  }
  return response.json();
}

export async function fetchCdpStatus(cdpUrl: string): Promise<{
  reachable: boolean;
  cdp_url: string;
  error?: string;
  browser?: string;
}> {
  const params = new URLSearchParams({ cdp_url: cdpUrl });
  const response = await fetch(`/api/imaginaire/cdp-status?${params}`);
  if (!response.ok) {
    throw new Error("Failed to check CDP status.");
  }
  return response.json();
}

export async function launchChrome(): Promise<{ cdp_url: string }> {
  const response = await fetch("/api/imaginaire/launch-chrome", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ open_deck_builder: true }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to launch Chrome.");
  }
  return response.json();
}

export async function createJob(body: {
  stores: string[];
  min_condition: string;
  decklist: string;
  browser_cdp_url?: string | null;
}): Promise<JobSummary> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to start job.");
  }
  return response.json();
}

export async function cancelJob(jobId: string): Promise<JobSummary> {
  const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Failed to cancel job.");
  }
  return response.json();
}

async function desktopBridgeApi(): Promise<DesktopBridgeApi | null> {
  if (window.pywebview?.api?.save_excel_export) {
    return window.pywebview.api;
  }
  await new Promise<void>((resolve) => {
    const onReady = () => {
      window.removeEventListener("pywebviewready", onReady);
      resolve();
    };
    window.addEventListener("pywebviewready", onReady);
    window.setTimeout(() => {
      window.removeEventListener("pywebviewready", onReady);
      resolve();
    }, 250);
  });
  return window.pywebview?.api?.save_excel_export ? window.pywebview.api : null;
}

type DesktopBridgeApi = NonNullable<NonNullable<Window["pywebview"]>["api"]>;

export async function downloadJobExcel(
  jobId: string,
  picks: Record<string, string>,
): Promise<void> {
  const inPywebview = typeof window.pywebview !== "undefined";
  const bridge = await desktopBridgeApi();

  // Desktop shell: blob/<a download> is a no-op in WebView2. Use the native
  // Save As bridge only — never silently fall back.
  if (inPywebview || bridge?.save_excel_export) {
    if (!bridge?.save_excel_export) {
      throw new Error(
        "Desktop Excel export is unavailable. Rebuild/restart the app and try again.",
      );
    }
    const result = await bridge.save_excel_export(jobId, picks);
    if (result.ok || result.cancelled) {
      return;
    }
    throw new Error(result.error ?? "Failed to export Excel.");
  }

  const response = await fetch(`/api/jobs/${jobId}/export.xlsx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ picks }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? "Failed to export Excel.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "mtg-prices.xlsx";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function subscribeJobEvents(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as JobEvent);
    } catch (error) {
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  };
  source.onerror = () => {
    onError?.(new Error("Lost connection to job progress stream."));
    source.close();
  };
  return () => source.close();
}
