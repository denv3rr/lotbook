import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, apiPut, invalidateApiCache } from "../../lib/api";
import { Modal } from "../ui/Modal";

type Lot = { qty: number | string; basis: number | string; timestamp: string; source?: string; kind?: string };
type Position = {
  ticker: string;
  quantity: string | null;
  lot_quantity: string;
  lot_count: number;
  lots: Lot[];
  total_basis: string | null;
  average_basis: string | null;
  mode: string;
  currency?: string | null;
  source_note?: string;
  warnings: string[];
};
type CashRow = { currency: string; amount: string };
type LedgerRow = {
  id: number;
  occurred_at: string;
  kind: string;
  ticker: string | null;
  quantity: string | null;
  cash_amount: string;
  currency: string;
  fee_amount: string;
  source_note: string;
  realized_pnl?: string | null;
};
type Book = {
  account_id: string;
  revision: string;
  positions: Position[];
  cash: CashRow[];
  ledger: LedgerRow[];
  warnings?: string[];
};
type Performance = {
  realized_pnl: string | null;
  fees: string | null;
  twr: number | null;
  xirr: number | null;
  warnings?: string[];
};

const emptyLot = { ticker: "", qty: "", basis: "", timestamp: "", source_note: "", currency: "USD" };
const emptyCash = { currency: "USD", amount: "", source_note: "", confirm: false };
const emptyTxn = {
  occurred_at: "",
  kind: "deposit",
  ticker: "",
  quantity: "",
  unit_price: "",
  cash_amount: "",
  currency: "USD",
  fee_amount: "0",
  source_note: "",
  confirm: false,
};

function isStale(reason: unknown): boolean {
  const message = reason instanceof Error ? reason.message : String(reason || "");
  return message.includes("409") || /changed (concurrently|since)/i.test(message);
}

function cashOnHand(book: Book | null, currency: string): number {
  const row = book?.cash.find((item) => item.currency === currency);
  return row ? Number(row.amount) : 0;
}

export function PositionsBook({
  clientId,
  accountId,
  disabled,
  onSaved,
}: {
  clientId: string;
  accountId: string;
  disabled?: boolean;
  onSaved: () => Promise<void> | void;
}) {
  const [book, setBook] = useState<Book | null>(null);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lotForm, setLotForm] = useState(emptyLot);
  const [cashForm, setCashForm] = useState(emptyCash);
  const [txnForm, setTxnForm] = useState(emptyTxn);
  const [importText, setImportText] = useState("");
  const [preview, setPreview] = useState<{ events: { kind: string; ticker: string | null; cash_amount: string; occurred_at?: string }[]; errors: { index: number; message: string }[]; would_write: boolean } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [pendingLot, setPendingLot] = useState<{ ticker: string; index: number } | null>(null);

  async function load() {
    setError(null);
    setStale(false);
    try {
      const payload = await apiGet<{ accounts: Book[] }>(`/api/clients/${encodeURIComponent(clientId)}/positions`);
      const match = payload.accounts.find((row) => row.account_id === accountId) || null;
      setBook(match);
      if (!match) setError("This account has no recorded book yet.");
      const stats = await apiGet<Performance>(`/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/performance`);
      setPerformance(stats);
    } catch (reason) {
      setBook(null);
      setError(reason instanceof Error ? reason.message : "Positions could not be loaded.");
    }
  }

  useEffect(() => {
    void load();
  }, [clientId, accountId]);

  async function saved(next: Book) {
    setBook(next);
    setStale(false);
    invalidateApiCache("/api/clients/");
    await onSaved();
    try {
      setPerformance(await apiGet<Performance>(`/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/performance`));
    } catch {
      setPerformance(null);
    }
  }

  function fail(reason: unknown, fallback: string) {
    if (isStale(reason)) {
      setStale(true);
      setError("This book was saved somewhere else. Reload before editing again so you do not overwrite later work.");
      return;
    }
    setError(reason instanceof Error ? reason.message : fallback);
  }

  async function writeLots(ticker: string, lots: Lot[], sourceNote: string) {
    if (!book) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPut<Book>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/positions`,
        { expected_revision: book.revision, ticker, mode: "lots", lots, currency: lotForm.currency, source_note: sourceNote }
      );
      setLotForm(emptyLot);
      await saved(next);
    } catch (reason) {
      fail(reason, "Lot update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function addLot(event: FormEvent) {
    event.preventDefault();
    if (!book) return;
    const ticker = lotForm.ticker.trim().toUpperCase();
    const existing = book.positions.find((row) => row.ticker === ticker);
    const lots = [
      ...((existing?.lots || []).map((lot) => ({ qty: lot.qty, basis: lot.basis, timestamp: lot.timestamp, source: lot.source, kind: lot.kind }))),
      { qty: lotForm.qty, basis: lotForm.basis, timestamp: lotForm.timestamp, kind: "lot", source: "CUSTOM" },
    ];
    await writeLots(ticker, lots, lotForm.source_note);
  }

  async function removeLot() {
    if (!book || !pendingLot) return;
    const position = book.positions.find((row) => row.ticker === pendingLot.ticker);
    if (!position) return;
    const remaining = position.lots.filter((_, index) => index !== pendingLot.index);
    setPendingLot(null);
    if (!remaining.length) {
      setPendingDelete(pendingLot.ticker);
      return;
    }
    await writeLots(pendingLot.ticker, remaining, `Removed ${pendingLot.ticker} lot ${pendingLot.index + 1}.`);
  }

  async function removePosition(ticker: string) {
    if (!book) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPut<Book>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/positions`,
        { expected_revision: book.revision, ticker, mode: "delete", confirm: true, source_note: `Removed ${ticker} from the recorded book.` }
      );
      setPendingDelete(null);
      await saved(next);
    } catch (reason) {
      fail(reason, "Removal failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveCash(event: FormEvent) {
    event.preventDefault();
    if (!book) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPut<Book>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/cash`,
        {
          expected_revision: book.revision,
          currency: cashForm.currency,
          amount: cashForm.amount,
          source_note: cashForm.source_note,
          confirm: cashForm.confirm || Number(cashForm.amount) < 0,
        }
      );
      setCashForm(emptyCash);
      await saved(next);
    } catch (reason) {
      fail(reason, "Cash update failed.");
    } finally {
      setBusy(false);
    }
  }

  const cashImpact = useMemo(() => {
    const qty = Number(txnForm.quantity);
    const price = Number(txnForm.unit_price);
    const fee = Number(txnForm.fee_amount || 0);
    if (txnForm.kind === "buy" && qty > 0 && price >= 0) return -(qty * price + fee);
    if (txnForm.kind === "sell" && qty > 0 && price >= 0) return qty * price - fee;
    if (txnForm.kind === "deposit" && Number(txnForm.cash_amount) > 0) return Number(txnForm.cash_amount);
    if ((txnForm.kind === "withdrawal" || txnForm.kind === "fee") && Number(txnForm.cash_amount)) return -Math.abs(Number(txnForm.cash_amount));
    return null;
  }, [txnForm]);

  const wouldOverdraw = cashImpact != null && cashOnHand(book, txnForm.currency) + cashImpact < 0;

  async function saveTransaction(event: FormEvent) {
    event.preventDefault();
    if (!book) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        expected_revision: book.revision,
        occurred_at: txnForm.occurred_at,
        kind: txnForm.kind,
        currency: txnForm.currency,
        source_note: txnForm.source_note,
        confirm: txnForm.confirm || wouldOverdraw,
      };
      if (txnForm.ticker) body.ticker = txnForm.ticker;
      if (txnForm.quantity) body.quantity = txnForm.quantity;
      if (txnForm.unit_price) body.unit_price = txnForm.unit_price;
      if (txnForm.cash_amount) body.cash_amount = txnForm.cash_amount;
      if (txnForm.fee_amount) body.fee_amount = txnForm.fee_amount;
      const next = await apiPost<Book>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/transactions`,
        body
      );
      setTxnForm(emptyTxn);
      await saved(next);
    } catch (reason) {
      fail(reason, "Transaction failed.");
    } finally {
      setBusy(false);
    }
  }

  function parseImport(): Array<Record<string, string>> {
    const lines = importText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (lines.length < 2) return [];
    const headers = lines[0].split(",").map((part) => part.trim());
    return lines.slice(1).map((line) => {
      const cells = line.split(",").map((part) => part.trim());
      const row: Record<string, string> = {};
      headers.forEach((header, index) => {
        row[header] = cells[index] || "";
      });
      return row;
    });
  }

  function importRows() {
    return parseImport().map((row) => ({
      occurred_at: row.occurred_at,
      kind: row.kind,
      ticker: row.ticker || null,
      quantity: row.quantity || null,
      unit_price: row.unit_price || null,
      cash_amount: row.cash_amount || null,
      currency: row.currency || "USD",
      fee_amount: row.fee_amount || "0",
      source_note: row.source_note,
      confirm: row.confirm === "true",
    }));
  }

  async function previewImport(event: FormEvent) {
    event.preventDefault();
    if (!book) return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiPost<{ events: { kind: string; ticker: string | null; cash_amount: string; occurred_at?: string }[]; errors: { index: number; message: string }[]; would_write: boolean }>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/transactions/import`,
        { expected_revision: book.revision, rows: importRows(), confirm: false }
      );
      setPreview(result);
    } catch (reason) {
      fail(reason, "Import preview failed.");
    } finally {
      setBusy(false);
    }
  }

  async function applyImport() {
    if (!book || !preview?.would_write) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<Book>(
        `/api/clients/${encodeURIComponent(clientId)}/accounts/${encodeURIComponent(accountId)}/transactions/import`,
        { expected_revision: book.revision, rows: importRows(), confirm: true }
      );
      setPreview(null);
      setImportText("");
      await saved(next);
    } catch (reason) {
      fail(reason, "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  const locked = disabled || busy || !book;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-xs text-slate-200">
        <p className="font-semibold text-emerald-200">Recorded book — this is where you edit lots and cash</p>
        <p className="mt-1 text-slate-400">Market prices live in the snapshot below and do not change quantities. Unrelated tickers stay unchanged.</p>
        {book ? <p className="mt-1 text-slate-500">Book revision {book.revision.slice(0, 12)}…</p> : null}
      </div>
      {stale ? (
        <div role="alert" className="rounded-xl border border-amber-400/50 p-3 text-xs text-amber-200">
          <p>{error}</p>
          <button type="button" className="mt-2 rounded-full border border-amber-400/60 px-3 py-1" onClick={() => void load()}>Reload book</button>
        </div>
      ) : error ? <p role="alert" className="text-xs text-amber-200">{error}</p> : null}
      {performance ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="rounded-xl border border-slate-700 p-3"><p className="text-slate-400">Realized P&amp;L</p><p>{performance.realized_pnl ?? "Unavailable"}</p></div>
          <div className="rounded-xl border border-slate-700 p-3"><p className="text-slate-400">Fees</p><p>{performance.fees ?? "Unavailable"}</p></div>
          <div className="rounded-xl border border-slate-700 p-3"><p className="text-slate-400">TWR / XIRR</p><p>{performance.twr == null && performance.xirr == null ? "Unavailable until an ending market value is recorded" : `${performance.twr ?? "—"} / ${performance.xirr ?? "—"}`}</p></div>
        </div>
      ) : null}
      {book?.cash?.length ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {book.cash.map((row) => (
            <div key={row.currency} className="rounded-xl border border-slate-700 p-3 text-xs">
              <p className="text-slate-400">{row.currency} cash</p>
              <p className="text-slate-100">{row.amount}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-400">No cash balances recorded. Use Cash correction below to set an opening balance.</p>
      )}
      {book?.positions?.length ? (
        <div className="space-y-3">
          {book.positions.map((position) => (
            <article key={position.ticker} className="rounded-xl border border-slate-700 p-4 text-xs text-slate-100">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-medium">{position.ticker}</h3>
                <button type="button" disabled={locked} onClick={() => setPendingDelete(position.ticker)} className="rounded-full border border-slate-700 px-3 py-1">
                  Remove all {position.ticker} lots
                </button>
              </div>
              <p>Quantity {position.quantity ?? "—"} · Lot qty {position.lot_quantity} · Average basis {position.average_basis ?? "unavailable"}</p>
              {position.warnings.map((warning) => <p key={warning} className="text-amber-200">{warning}</p>)}
              {(position.lots || []).map((lot, index) => (
                <div key={`${position.ticker}-${index}`} className="mt-2 flex flex-wrap items-center justify-between gap-2 text-slate-300">
                  <p>Lot {index + 1}: {String(lot.qty)} @ {String(lot.basis)} · {lot.timestamp}</p>
                  <button type="button" disabled={locked} className="rounded-full border border-slate-700 px-3 py-1" onClick={() => setPendingLot({ ticker: position.ticker, index })}>Remove this lot</button>
                </div>
              ))}
            </article>
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-400">No lots recorded. Add a lot below with ticker, quantity, per-unit basis, date, and a source note.</p>
      )}
      <form className="rounded-xl border border-slate-700 p-4 space-y-3" onSubmit={addLot}>
        <h3 className="text-xs font-semibold text-slate-200">Add a lot</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="text-xs text-slate-400">Ticker<input required value={lotForm.ticker} onChange={(event) => setLotForm({ ...lotForm, ticker: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Quantity<input required type="number" step="any" min="0" value={lotForm.qty} onChange={(event) => setLotForm({ ...lotForm, qty: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Per-unit basis<input required type="number" step="any" min="0" value={lotForm.basis} onChange={(event) => setLotForm({ ...lotForm, basis: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Acquisition date<input required type="date" value={lotForm.timestamp} onChange={(event) => setLotForm({ ...lotForm, timestamp: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400 md:col-span-2">Source / reason<input required maxLength={1000} value={lotForm.source_note} onChange={(event) => setLotForm({ ...lotForm, source_note: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
        </div>
        <button type="submit" disabled={locked} className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200">{busy ? "Saving..." : "Save lot"}</button>
      </form>
      <form className="rounded-xl border border-slate-700 p-4 space-y-3" onSubmit={saveCash}>
        <h3 className="text-xs font-semibold text-slate-200">Set cash balance</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="text-xs text-slate-400">Currency<input required maxLength={3} value={cashForm.currency} onChange={(event) => setCashForm({ ...cashForm, currency: event.target.value.toUpperCase() })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Amount<input required type="number" step="any" value={cashForm.amount} onChange={(event) => setCashForm({ ...cashForm, amount: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Source / reason<input required value={cashForm.source_note} onChange={(event) => setCashForm({ ...cashForm, source_note: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={cashForm.confirm} onChange={(event) => setCashForm({ ...cashForm, confirm: event.target.checked })} /> I confirm a negative cash balance if entered</label>
        <button type="submit" disabled={locked} className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200">Save cash</button>
      </form>
      <form className="rounded-xl border border-slate-700 p-4 space-y-3" onSubmit={saveTransaction}>
        <h3 className="text-xs font-semibold text-slate-200">Record a buy, sell, or cash event</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="text-xs text-slate-400">Occurred at<input required type="datetime-local" value={txnForm.occurred_at} onChange={(event) => setTxnForm({ ...txnForm, occurred_at: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Kind
            <select aria-label="Event kind" value={txnForm.kind} onChange={(event) => setTxnForm({ ...txnForm, kind: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200">
              {["buy", "sell", "deposit", "withdrawal", "fee", "transfer_in", "transfer_out", "dividend", "interest", "split"].map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-400">Ticker<input value={txnForm.ticker} onChange={(event) => setTxnForm({ ...txnForm, ticker: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Quantity<input type="number" step="any" value={txnForm.quantity} onChange={(event) => setTxnForm({ ...txnForm, quantity: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Unit price<input type="number" step="any" value={txnForm.unit_price} onChange={(event) => setTxnForm({ ...txnForm, unit_price: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400">Cash amount<input type="number" step="any" value={txnForm.cash_amount} onChange={(event) => setTxnForm({ ...txnForm, cash_amount: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
          <label className="text-xs text-slate-400 md:col-span-2">Source / reason<input required value={txnForm.source_note} onChange={(event) => setTxnForm({ ...txnForm, source_note: event.target.value })} className="mt-1 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" /></label>
        </div>
        {cashImpact != null ? <p className="text-xs text-slate-300">This event would change {txnForm.currency} cash by {cashImpact.toFixed(2)}. Current recorded cash is {cashOnHand(book, txnForm.currency).toFixed(2)}.</p> : null}
        {wouldOverdraw ? <label className="flex items-center gap-2 text-xs text-amber-200"><input type="checkbox" checked={txnForm.confirm} onChange={(event) => setTxnForm({ ...txnForm, confirm: event.target.checked })} required /> This would overdraw recorded cash. Confirm to save it as an explicit correction.</label> : null}
        <button type="submit" disabled={locked} className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200">Record event</button>
      </form>
      <form className="rounded-xl border border-slate-700 p-4 space-y-3" onSubmit={previewImport}>
        <h3 className="text-xs font-semibold text-slate-200">Import transactions</h3>
        <p className="text-xs text-slate-400">CSV header: occurred_at,kind,ticker,quantity,unit_price,cash_amount,currency,fee_amount,source_note,confirm</p>
        <label className="text-xs text-slate-400">CSV file<input type="file" accept=".csv,text/csv,text/plain" onChange={(event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          void file.text().then(setImportText);
        }} className="mt-1 block text-slate-200" /></label>
        <textarea aria-label="Import CSV text" value={importText} onChange={(event) => setImportText(event.target.value)} rows={5} className="w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200" />
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={locked} className="rounded-full border border-slate-500 px-4 py-1 text-xs">Preview import</button>
          <button type="button" disabled={locked || !preview?.would_write} onClick={() => void applyImport()} className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200">Apply import</button>
        </div>
        {preview ? (
          <div className="overflow-x-auto text-xs text-slate-300">
            <p>{preview.events.length} events ready. {preview.errors.length} blocking errors.</p>
            {preview.events.length ? (
              <table className="mt-2 w-full border-collapse">
                <thead><tr><th className="border border-slate-700 p-1 text-left">Kind</th><th className="border border-slate-700 p-1 text-left">Ticker</th><th className="border border-slate-700 p-1 text-left">Cash</th></tr></thead>
                <tbody>{preview.events.map((event, index) => <tr key={`${event.kind}-${index}`}><td className="border border-slate-700 p-1">{event.kind}</td><td className="border border-slate-700 p-1">{event.ticker || "—"}</td><td className="border border-slate-700 p-1">{event.cash_amount}</td></tr>)}</tbody>
              </table>
            ) : null}
            {preview.errors.map((item) => <p key={item.index} className="text-amber-200">Row {item.index + 1}: {item.message}</p>)}
          </div>
        ) : null}
      </form>
      {book?.ledger?.length ? (
        <div className="rounded-xl border border-slate-700 p-4 text-xs space-y-2">
          <h3 className="font-semibold text-slate-200">Correction and cash-flow history</h3>
          {book.ledger.map((row) => (
            <p key={row.id}>{row.occurred_at} · {row.kind} · {row.ticker || row.currency} · {row.cash_amount} · {row.source_note}</p>
          ))}
        </div>
      ) : null}
      <Modal open={Boolean(pendingDelete)} title="Remove position" description="This deletes the recorded lots for one ticker and leaves every other holding unchanged." onClose={() => setPendingDelete(null)} footer={
        <>
          <button type="button" className="rounded-full border border-slate-700 px-3 py-1 text-[11px]" onClick={() => setPendingDelete(null)}>Cancel</button>
          <button type="button" className="rounded-full border border-amber-400/60 px-3 py-1 text-[11px] text-amber-200" disabled={busy} onClick={() => pendingDelete && void removePosition(pendingDelete)}>Remove</button>
        </>
      }>
        <p>Remove {pendingDelete}? This cannot be undone except by recording a new lot.</p>
      </Modal>
      <Modal open={Boolean(pendingLot)} title="Remove lot" description="Other lots for this ticker stay in place." onClose={() => setPendingLot(null)} footer={
        <>
          <button type="button" className="rounded-full border border-slate-700 px-3 py-1 text-[11px]" onClick={() => setPendingLot(null)}>Cancel</button>
          <button type="button" className="rounded-full border border-amber-400/60 px-3 py-1 text-[11px] text-amber-200" disabled={busy} onClick={() => void removeLot()}>Remove lot</button>
        </>
      }>
        <p>Remove {pendingLot?.ticker} lot {(pendingLot?.index ?? 0) + 1}?</p>
      </Modal>
    </div>
  );
}
