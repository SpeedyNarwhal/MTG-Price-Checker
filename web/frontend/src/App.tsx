import { useEffect, useMemo, useState } from "react";
import {
  cancelJob,
  createJob,
  fetchCdpStatus,
  fetchStores,
  subscribeJobEvents,
} from "./api";
import type { JobResults, StoreInfo } from "./types";

type Screen = "setup" | "running" | "results";

const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"] as const;

const DEFAULT_STORES = [
  "danireon",
  "silvergoblin",
  "facetoface",
  "hobbiesville",
  "wizardtower",
];

const DONT_BUY = "__dont_buy__";

function cheapestStoreId(row: JobResults["cards"][number]): string | null {
  let bestId: string | null = null;
  let bestPrice = Number.POSITIVE_INFINITY;
  for (const cell of row.stores) {
    if (cell.status !== "FOUND" || cell.price_cad == null) {
      continue;
    }
    const price = Number(cell.price_cad);
    if (price < bestPrice) {
      bestPrice = price;
      bestId = cell.store_id;
    }
  }
  return bestId;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("setup");
  const [stores, setStores] = useState<StoreInfo[]>([]);
  const [selectedStores, setSelectedStores] = useState<string[]>(DEFAULT_STORES);
  const [minCondition, setMinCondition] = useState<string>("NM");
  const [decklist, setDecklist] = useState("");
  const [cdpUrl, setCdpUrl] = useState("http://127.0.0.1:9222");
  const [cdpReachable, setCdpReachable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState("Starting…");
  const [cardIndex, setCardIndex] = useState(0);
  const [totalCards, setTotalCards] = useState(0);
  const [results, setResults] = useState<JobResults | null>(null);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [copiedStore, setCopiedStore] = useState<string | null>(null);

  const imaginaireSelected = selectedStores.includes("imaginaire");

  useEffect(() => {
    fetchStores()
      .then((payload) => {
        setStores(payload.stores);
        setCdpUrl(payload.default_cdp_url);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!imaginaireSelected) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const status = await fetchCdpStatus(cdpUrl);
        if (!cancelled) {
          setCdpReachable(Boolean(status.reachable));
        }
      } catch {
        if (!cancelled) {
          setCdpReachable(false);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [imaginaireSelected, cdpUrl]);

  const progressPct = totalCards > 0 ? Math.min(100, (cardIndex / totalCards) * 100) : 0;

  const cartTotal = useMemo(() => {
    if (!results) {
      return 0;
    }
    let total = 0;
    for (const card of results.cards) {
      const storeId = picks[card.card_name];
      if (!storeId || storeId === DONT_BUY) {
        continue;
      }
      const cell = card.stores.find((entry) => entry.store_id === storeId);
      if (cell?.status === "FOUND" && cell.price_cad != null) {
        total += Number(cell.price_cad) * card.quantity;
      }
    }
    return total;
  }, [results, picks]);

  const shoppingLists = useMemo(() => {
    if (!results) {
      return [];
    }
    return results.stores
      .map((store) => {
        const lines: string[] = [];
        let subtotal = 0;
        for (const card of results.cards) {
          if (picks[card.card_name] !== store.store_id) {
            continue;
          }
          const cell = card.stores.find((entry) => entry.store_id === store.store_id);
          if (cell?.status !== "FOUND" || cell.price_cad == null) {
            continue;
          }
          lines.push(`${card.quantity} ${card.card_name}`);
          subtotal += Number(cell.price_cad) * card.quantity;
        }
        return {
          store_id: store.store_id,
          display_name: store.display_name,
          lines,
          text: lines.join("\n"),
          subtotal,
        };
      })
      .filter((entry) => entry.lines.length > 0);
  }, [results, picks]);

  function toggleStore(storeId: string) {
    setSelectedStores((current) =>
      current.includes(storeId)
        ? current.filter((id) => id !== storeId)
        : [...current, storeId],
    );
  }

  async function onStart() {
    setError(null);
    if (selectedStores.length === 0) {
      setError("Select at least one store.");
      return;
    }
    if (!decklist.trim()) {
      setError("Paste a decklist first.");
      return;
    }

    try {
      const job = await createJob({
        stores: selectedStores,
        min_condition: minCondition,
        decklist,
        browser_cdp_url: imaginaireSelected ? cdpUrl : null,
      });
      setJobId(job.job_id);
      setCardIndex(job.card_index);
      setTotalCards(job.total_cards);
      setProgressMessage(job.message);
      setScreen("running");

      const unsubscribe = subscribeJobEvents(
        job.job_id,
        (event) => {
          if (event.type === "progress") {
            setCardIndex(event.card_index);
            setTotalCards(event.total_cards);
            setProgressMessage(event.message);
            return;
          }
          if (event.type === "status" || event.type === "heartbeat") {
            if ("message" in event && event.message) {
              setProgressMessage(event.message);
            }
            return;
          }
          if (event.type === "done" || event.type === "cancelled") {
            setProgressMessage(event.message);
            setResults(event.results);
            const nextPicks: Record<string, string> = {};
            for (const card of event.results.cards) {
              nextPicks[card.card_name] = cheapestStoreId(card) ?? DONT_BUY;
            }
            setPicks(nextPicks);
            setScreen("results");
            unsubscribe();
            return;
          }
          if (event.type === "error") {
            setError(event.message);
            setScreen("setup");
            unsubscribe();
          }
        },
        (err) => {
          setError(err.message);
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onCancel() {
    if (!jobId) {
      return;
    }
    try {
      await cancelJob(jobId);
      setProgressMessage("Cancel requested…");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function copyList(storeId: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopiedStore(storeId);
    window.setTimeout(() => setCopiedStore(null), 1500);
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <h1>MTG Price Checker</h1>
        <p>
          Compare Canadian store prices, pick where to buy each card, and copy shopping lists
          per store.
        </p>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      {screen === "setup" ? (
        <section className="panel stack">
          <div>
            <h2>Stores</h2>
            <div className="store-grid">
              {stores.map((store) => (
                <label className="store-option" key={store.store_id}>
                  <input
                    type="checkbox"
                    checked={selectedStores.includes(store.store_id)}
                    onChange={() => toggleStore(store.store_id)}
                  />
                  <span>{store.display_name}</span>
                </label>
              ))}
            </div>
          </div>

          <label className="field">
            Minimum condition
            <select
              className="select-input"
              value={minCondition}
              onChange={(event) => setMinCondition(event.target.value)}
            >
              {CONDITIONS.map((condition) => (
                <option key={condition} value={condition}>
                  {condition}
                </option>
              ))}
            </select>
          </label>

          {imaginaireSelected ? (
            <div className="helper">
              <h3>Imaginaire</h3>
              <p className="muted" style={{ margin: 0 }}>
                Chrome opens automatically when you start, then closes when the run finishes. If
                Cloudflare appears, solve it in that Chrome window.
              </p>
              <div className="row" style={{ marginTop: "0.75rem" }}>
                <span className={`status-pill ${cdpReachable ? "status-ok" : "status-bad"}`}>
                  {cdpReachable ? "Chrome already ready" : "Will launch Chrome"}
                </span>
              </div>
            </div>
          ) : null}

          <label className="field">
            Decklist
            <textarea
              className="decklist"
              value={decklist}
              onChange={(event) => setDecklist(event.target.value)}
              placeholder={"4 Sol Ring\nArcane Signet\n# comments are ignored"}
            />
          </label>

          <div className="row">
            <button type="button" className="btn btn-primary" onClick={() => void onStart()}>
              Start price check
            </button>
          </div>
        </section>
      ) : null}

      {screen === "running" ? (
        <section className="panel progress-wrap">
          <h2>Checking prices…</h2>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="muted">
            {cardIndex}/{totalCards || "?"} cards
          </div>
          <p>{progressMessage}</p>
          <div className="row">
            <button type="button" className="btn btn-danger" onClick={() => void onCancel()}>
              Cancel
            </button>
          </div>
        </section>
      ) : null}

      {screen === "results" && results ? (
        <section className="stack">
          <div className="panel totals">
            <div>
              <div className="muted">Selected cart total</div>
              <strong>${cartTotal.toFixed(2)} CAD</strong>
            </div>
            <div className="row">
              <button type="button" className="btn btn-secondary" onClick={() => setScreen("setup")}>
                New search
              </button>
            </div>
          </div>

          <div className="panel stack">
            <h2>Price matrix</h2>
            <p className="muted">
              Cheapest in-stock cells are highlighted. Change the Buy at store to rebuild shopping
              lists.
            </p>
            <div className="table-wrap">
              <table className="matrix">
                <thead>
                  <tr>
                    <th>Card</th>
                    <th>Buy at</th>
                    {results.stores.map((store) => (
                      <th key={store.store_id}>{store.display_name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.cards.map((card) => {
                    const best = cheapestStoreId(card);
                    return (
                      <tr key={card.card_name}>
                        <td>
                          {card.quantity > 1 ? `${card.quantity}× ` : ""}
                          {card.card_name}
                        </td>
                        <td>
                          <select
                            className="select-input"
                            value={picks[card.card_name] ?? DONT_BUY}
                            onChange={(event) =>
                              setPicks((current) => ({
                                ...current,
                                [card.card_name]: event.target.value,
                              }))
                            }
                          >
                            <option value={DONT_BUY}>Don't buy</option>
                            {card.stores
                              .filter((cell) => cell.status === "FOUND")
                              .map((cell) => {
                                const store = results.stores.find(
                                  (entry) => entry.store_id === cell.store_id,
                                );
                                return (
                                  <option key={cell.store_id} value={cell.store_id}>
                                    {store?.display_name ?? cell.store_id}
                                    {cell.price_cad ? ` ($${cell.price_cad})` : ""}
                                  </option>
                                );
                              })}
                          </select>
                        </td>
                        {card.stores.map((cell) => {
                          const isCheapest =
                            cell.store_id === best && cell.status === "FOUND";
                          return (
                            <td
                              key={cell.store_id}
                              className={isCheapest ? "cell-cheapest" : undefined}
                            >
                              {cell.status === "FOUND" && cell.price_cad ? (
                                cell.product_url ? (
                                  <a
                                    className="cell-price"
                                    href={cell.product_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    ${cell.price_cad}
                                  </a>
                                ) : (
                                  <span className="cell-price">${cell.price_cad}</span>
                                )
                              ) : (
                                <span className="cell-status">{cell.status}</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel stack">
            <h2>Shopping lists</h2>
            {shoppingLists.length === 0 ? (
              <p className="muted">No FOUND picks yet.</p>
            ) : (
              <div className="store-lists">
                {shoppingLists.map((list) => (
                  <div className="store-list" key={list.store_id}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <strong>{list.display_name}</strong>
                      <span className="muted">
                        {list.lines.length} cards · ${list.subtotal.toFixed(2)}
                      </span>
                    </div>
                    <pre>{list.text}</pre>
                    <div className="row">
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => void copyList(list.store_id, list.text)}
                      >
                        Copy list
                      </button>
                      {copiedStore === list.store_id ? (
                        <span className="copied">Copied</span>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
