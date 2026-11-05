export type StoreInfo = {
  store_id: string;
  display_name: string;
  requires_cdp?: boolean;
};

export type StoreCell = {
  store_id: string;
  status: string;
  price_cad: string | null;
  product_url: string | null;
  notes: string | null;
};

export type CardRow = {
  card_name: string;
  quantity: number;
  stores: StoreCell[];
};

export type JobResults = {
  stores: { store_id: string; display_name: string }[];
  cards: CardRow[];
};

export type JobSummary = {
  job_id: string;
  status: string;
  message: string;
  card_index: number;
  total_cards: number;
  error: string | null;
  stores: string[];
  min_condition: string;
  browser_cdp_url: string | null;
  results: JobResults | null;
};

export type ProgressEvent = {
  type: "progress";
  card_index: number;
  total_cards: number;
  card_name: string;
  message: string;
  store_statuses: Record<string, string>;
};

export type JobEvent =
  | ProgressEvent
  | { type: "status"; status: string; message: string }
  | { type: "heartbeat"; status: string }
  | { type: "done"; status: string; message: string; results: JobResults }
  | { type: "cancelled"; status: string; message: string; results: JobResults }
  | { type: "error"; status: string; message: string; error: string };
