import { useState } from "react";
import { apiPost, useApi } from "../../lib/api";
import { Modal } from "../ui/Modal";

export function CloseApp({ onCancel, onStopping }: { onCancel: () => void; onStopping: () => void }) {
  const status = useApi<{ shutdown_available: boolean; message: string }>("/api/application/status");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function close() {
    setBusy(true); setError("");
    try { await apiPost("/api/application/shutdown", { confirm: true }); onStopping(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Shutdown request failed."); setBusy(false); }
  }
  return <Modal open title="Close Lotbook?" description="This closes the local API and dashboard server for this Lotbook session. Saved records stay on disk. Finish or save any open edits first." onClose={() => { if (!busy) onCancel(); }}>
    {(status.error || error) && <p role="alert" className="bank-error">{error || status.error}</p>}
    {!status.loading && status.data && !status.data.shutdown_available && <p className="bank-error">{status.data.message}</p>}
    <div className="bank-form-actions"><button className="bank-button" onClick={onCancel} disabled={busy}>Keep working</button><button className="bank-button bank-primary" disabled={busy || status.loading || !status.data?.shutdown_available || Boolean(status.error)} onClick={close}>{busy ? "Requesting shutdown…" : "Close Lotbook safely"}</button></div>
  </Modal>;
}
