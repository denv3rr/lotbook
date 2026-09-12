import { useState, type FormEvent } from "react";
import { apiPost, useApi } from "../../lib/api";
import { downloadJson, type BankRecord, type Workspace } from "../../lib/banking";

export function ModelArchive({ kind, inputs, disabled, onLoad }: { kind: "dcf" | "comps"; inputs: Record<string, unknown> | null; disabled: boolean; onLoad: (inputs: Record<string, unknown>) => void }) {
  const api = useApi<Workspace & { valuations: BankRecord[] }>("/api/banking/workspace");
  const [client, setClient] = useState("");
  const [prior, setPrior] = useState<BankRecord | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    const form = new FormData(event.currentTarget);
    try {
      await apiPost("/api/banking/valuations", { name: form.get("name"), owner: form.get("owner"), source_note: inputs?.source_note, client_id: client, deal_id: form.get("deal_id") || null, supersedes_id: prior?.id || null, model_kind: kind, inputs });
      setNotice("Valuation saved with its assumptions and calculated results."); api.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save valuation."); }
    finally { setBusy(false); }
  }
  return <section className="bank-panel bank-padded"><h2>Saved models & versions</h2><p className="bank-muted">Each save creates an immutable snapshot. Load assumptions, revise and recalculate to save a new version. Owner labels are not authenticated approvals.</p>
    {(error || api.error) && <p role="alert" className="bank-error">{error || api.error}</p>}<p role="status">{notice}</p>
    <form className="bank-form" onSubmit={save}><label className="bank-field"><span>Model name *</span><input name="name" required maxLength={160} /></label><label className="bank-field"><span>Prepared by *</span><input name="owner" required maxLength={160} /></label>
      <label className="bank-field"><span>Model client *</span><select required value={client} disabled={Boolean(prior)} onChange={e => setClient(e.target.value)}><option value="">Select client</option>{api.data?.clients.map(row => <option key={row.client_id} value={row.client_id}>{row.name}</option>)}</select></label>
      <label className="bank-field"><span>Model deal</span><select name="deal_id" key={client}><option value="">Client-level valuation</option>{api.data?.deals.filter(row => row.client_id === client).map(row => <option value={row.id} key={row.id}>{String(row.name)}</option>)}</select></label>
      <div className="bank-actions bank-span"><button className="bank-button bank-primary" disabled={disabled || !inputs || busy || !api.data || Boolean(api.error)}>{busy ? "Saving…" : "Save model version"}</button>{prior && <button className="bank-button" type="button" onClick={() => setPrior(null)}>Start separate model</button>}<span className="bank-muted">{prior ? `New version of ${prior.name}` : "Calculate valid, current results before saving."}</span></div>
    </form>
    <button className="bank-text-button" onClick={() => api.refresh()}>Refresh saved models</button>
    <div className="bank-table-scroll"><table className="bank-table"><caption>Saved {kind === "dcf" ? "DCF" : "comparable"} valuations</caption><thead><tr><th>Model / client</th><th>Prepared by</th><th>Saved</th><th>Version</th><th>Actions</th></tr></thead><tbody>{api.data?.valuations?.filter(row => row.model_kind === kind).map(row => <tr key={row.id}><th scope="row">{String(row.name)}<span className="bank-subline">{api.data?.clients.find(client => client.client_id === row.client_id)?.name}</span></th><td>{row.owner}</td><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.supersedes_id ? "Revised snapshot" : "Original snapshot"}</td><td><button className="bank-text-button" onClick={() => { setPrior(row); setClient(row.client_id); onLoad(row.inputs as Record<string, unknown>); }}>Load assumptions</button><button className="bank-text-button" onClick={() => downloadJson(row, `lotbook-model-${row.id}.json`)}>Export snapshot</button></td></tr>)}</tbody></table></div>
    {!api.loading && !api.data?.valuations?.some(row => row.model_kind === kind) && <p className="bank-muted">No saved models of this type yet.</p>}
  </section>;
}
