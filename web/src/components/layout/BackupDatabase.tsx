import { useState, type FormEvent } from "react";
import { Modal } from "../ui/Modal";
import { getApiBase, getApiKey, getAuthHint } from "../../lib/api";

export function BackupDatabase() {
  const [open, setOpen] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  function close() { if (!busy) { setOpen(false); setPassphrase(""); setConfirmation(""); setError(null); } }
  async function download(event: FormEvent) {
    event.preventDefault(); setError(null);
    if (passphrase !== confirmation) { setError("Passphrases do not match."); return; }
    setBusy(true);
    try {
      const key = await getApiKey();
      if (!key) throw new Error("Configure the API key before exporting all client records.");
      const response = await fetch(`${getApiBase()}/api/application/backup`, { method: "POST", headers: { "Content-Type": "application/json", "X-API-Key": key, "X-Lotbook-Backup": "confirm" }, body: JSON.stringify({ confirm: true, passphrase }) });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) throw new Error(getAuthHint());
        const problem = await response.json();
        throw new Error(typeof problem.detail === "string" ? problem.detail : "Backup request was rejected.");
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `lotbook-database-${new Date().toISOString().slice(0, 10)}.lotbookbackup`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setOpen(false); setPassphrase(""); setConfirmation(""); setSaved(true);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Backup download failed."); }
    finally { setBusy(false); }
  }
  return <section className="mt-4 rounded-xl border border-slate-700 p-4 text-sm text-slate-200" aria-label="Database recovery">
    <h2 className="font-semibold">Encrypted database backup</h2>
    <p className="my-2 text-xs text-slate-300">Includes all canonical client, account and advisory records. Credentials, external documents and feed caches are not included. Local operator access and an API key are required.</p>
    <button type="button" className="globe-action-button" onClick={() => { setOpen(true); setSaved(false); }}>Download encrypted backup</button>
    {saved && <p role="status" className="mt-2">Encrypted backup download started. Keep its passphrase separately and verify recovery before relying on it.</p>}
    <Modal open={open} onClose={close} title="Export encrypted database backup" description="This exports all client records. Lotbook cannot recover a lost backup passphrase. Nothing in the running database is changed.">
      <form onSubmit={download} className="grid gap-4 p-5">
        <label className="grid gap-1">Backup passphrase<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={passphrase} onChange={event => setPassphrase(event.target.value)} className="rounded border border-slate-500 bg-slate-900 p-2" /></label>
        <label className="grid gap-1">Repeat backup passphrase<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirmation} onChange={event => setConfirmation(event.target.value)} className="rounded border border-slate-500 bg-slate-900 p-2" /></label>
        {error && <p role="alert" className="text-amber-200">{error}</p>}
        <div className="flex gap-3"><button type="button" disabled={busy} onClick={close} className="globe-action-button">Cancel</button><button type="submit" disabled={busy} className="globe-action-button">{busy ? "Creating snapshot…" : "Confirm and download backup"}</button></div>
      </form>
    </Modal>
  </section>;
}
