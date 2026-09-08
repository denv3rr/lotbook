import { useState, type FormEvent } from "react";
import { Modal } from "../ui/Modal";
import { apiPatch, apiPost } from "../../lib/api";
import { dealTypes, stages, taskStatuses, type Workspace, type BankRecord } from "../../lib/banking";

export type FormKind = "client" | "deal" | "contact" | "task";
export function RecordForm({ kind, record, workspace, clientId, onClose, onSaved }: {
  kind: FormKind; record?: BankRecord; workspace: Workspace; clientId?: string; onClose: () => void; onSaved: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [selectedClient, setSelectedClient] = useState(record?.client_id || clientId || "");
  const [dealId, setDealId] = useState(String(record?.deal_id || ""));
  const values: Record<string, unknown> = record || {};
  const input = (name: string, caption: string, props: Record<string, unknown> = {}) => <label className="bank-field" key={name}><span>{caption}</span><input name={name} defaultValue={String(values[name] ?? "")} maxLength={160} {...props} /></label>;
  const select = (name: string, caption: string, choices: Record<string, string>, fallback: string) => <label className="bank-field"><span>{caption}</span><select name={name} defaultValue={String(values[name] || fallback)}>{Object.entries(choices).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>;
  const area = (name: string, caption: string, required = false) => <label className="bank-field bank-span"><span>{caption}</span><textarea name={name} defaultValue={String(values[name] ?? "")} required={required} maxLength={4000} rows={3} /></label>;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setSaving(true);
    const payload: Record<string, unknown> = Object.fromEntries([...new FormData(event.currentTarget).entries()].map(([key, value]) => [key, String(value).trim()]));
    if (kind === "client") payload.accounts = [];
    else if (record) payload.expected_revision = record.revision;
    else payload.client_id = selectedClient;
    if (kind === "deal") {
      for (const field of ["expected_value", "fee_bps", "target_close"]) payload[field] = payload[field] || null;
      payload.close_probability = payload.close_probability === "" ? null : Number(payload.close_probability) / 100;
    }
    if (kind === "task") { payload.deal_id = dealId || null; payload.due_date = payload.due_date || null; }
    try {
      const path = kind === "client" ? "/api/clients" : `/api/banking/${kind}s`;
      if (record) await apiPatch(`${path}/${encodeURIComponent(record.id)}`, payload);
      else await apiPost(path, payload);
      onSaved(); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save. Your entries are still here."); }
    finally { setSaving(false); }
  }
  return <Modal open title={`${record ? "Edit" : "New"} ${kind}`} description="Saved to your local workspace. Required fields are marked with an asterisk." onClose={() => { if (!saving) onClose(); }}>
    <form onSubmit={submit} className="bank-form">
      {error && <p role="alert" className="bank-error bank-span">{error}</p>}
      {kind !== "client" && <label className="bank-field bank-span"><span>Client *</span><select value={selectedClient} required disabled={Boolean(record)} onChange={event => { setSelectedClient(event.target.value); setDealId(""); }}><option value="">Select a client</option>{workspace.clients.map(client => <option value={client.client_id} key={client.client_id}>{client.name}</option>)}</select></label>}
      {kind === "client" && <>{input("name", "Client or company name *", { required: true })}<p className="bank-muted bank-span">Add contacts and mandates now, and investment accounts from the Clients page when needed.</p></>}
      {kind === "deal" && <>
        {input("name", "Deal name *", { required: true })}{select("deal_type", "Advisory service", dealTypes, "sell_side")}{select("stage", "Stage", stages, "prospect")}
        {input("owner", "Deal owner *", { required: true })}{input("currency", "Currency code *", { required: true, defaultValue: values.currency || "USD", pattern: "[A-Z]{3}", maxLength: 3 })}
        {input("expected_value", "Expected transaction value", { type: "number", min: 0, max: 1e18, step: "0.01" })}{input("fee_bps", "Success fee (basis points)", { type: "number", min: 0, max: 10000, step: "0.01" })}
        {input("close_probability", "Estimated close probability (%)", { type: "number", min: 0, max: 100, step: "0.01", defaultValue: values.close_probability == null ? "" : Number(values.close_probability) * 100 })}
        <p className="bank-muted bank-span">100 basis points = 1%. Leave unknown amounts blank. Close probability is your estimate and is never inferred from the stage.</p>
        {input("target_close", "Target close", { type: "date" })}{area("next_action", "Next action")}
      </>}
      {kind === "contact" && <>{input("name", "Contact name *", { required: true })}{input("title", "Job title")}{input("email", "Email", { type: "email", maxLength: 254 })}{input("phone", "Phone", { type: "tel", maxLength: 80 })}{input("owner", "Relationship owner *", { required: true })}{area("notes", "Relationship notes")}</>}
      {kind === "task" && <>{input("title", "Task title *", { required: true })}{input("owner", "Task owner *", { required: true })}
        <label className="bank-field"><span>Linked deal</span><select value={dealId} onChange={event => setDealId(event.target.value)}><option value="">Client-level task</option>{workspace.deals.filter(deal => deal.client_id === selectedClient).map(deal => <option value={deal.id} key={deal.id}>{String(deal.name)}</option>)}</select></label>
        {input("due_date", "Due date", { type: "date" })}{select("category", "Workstream", { follow_up: "Follow-up", diligence: "Diligence", meeting: "Meeting", deliverable: "Deliverable" }, "follow_up")}{select("status", "Status", taskStatuses, "open")}{area("notes", "Notes and response references")}</>}
      {kind !== "client" && area("source_note", "Source / basis for this record *", true)}
      <div className="bank-form-actions bank-span"><button className="bank-button" type="button" disabled={saving} onClick={onClose}>Cancel</button><button className="bank-button bank-primary" type="submit" disabled={saving}>{saving ? "Saving…" : `Save ${kind}`}</button></div>
    </form>
  </Modal>;
}
