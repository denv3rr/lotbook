import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiPost } from "../lib/api";
import { downloadJson, money } from "../lib/banking";
import { ModelArchive } from "../components/banking/ModelArchive";

type Peer = Record<string, unknown>;
type Result = { inputs: { currency: string }; warnings: string[]; peers: { name: string; ev_revenue: number | null; ev_ebitda: number | null }[]; summaries: { metric: string; included_peers: number; total_peers: number; cases: { label: string; multiple: number | null; enterprise_value: number | null; equity_value: number | null; value_per_share: number | null }[] }[] };
export default function Comparables() {
  const [peers, setPeers] = useState<Peer[]>([{}]);
  const [initial, setInitial] = useState<Record<string, unknown>>({});
  const [version, setVersion] = useState(0);
  const [inputs, setInputs] = useState<Record<string, unknown> | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [dirty, setDirty] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const field = (name: string, label: string, required = true, options: Record<string, unknown> = {}) => <label className="bank-field"><span>{label}{required ? " *" : ""}</span><input name={name} type="number" step="any" defaultValue={String(initial[name] ?? "")} required={required} {...options} /></label>;
  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const number = (key: string) => form.get(key) === "" ? null : Number(form.get(key));
    const body: Record<string, unknown> = Object.fromEntries(["currency", "as_of", "period_basis", "source_note"].map(key => [key, form.get(key)]));
    for (const key of ["target_revenue", "target_ebitda", "cash", "debt", "other_claims", "non_operating_assets", "diluted_shares"]) body[key] = number(key);
    body.peers = peers.map((_, i) => ({ name: form.get(`peer_${i}_name`), source_note: form.get(`peer_${i}_source_note`), enterprise_value: number(`peer_${i}_enterprise_value`), revenue: number(`peer_${i}_revenue`), ebitda: number(`peer_${i}_ebitda`) }));
    try { setResult(await apiPost<Result>("/api/banking/valuation/comps", body)); setInputs(body); setDirty(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Calculation failed."); }
    finally { setBusy(false); }
  }
  return <div className="bank-workspace"><header className="bank-heading"><div><p className="bank-eyebrow">COMPARABLE COMPANY ANALYSIS</p><h1>Put value in context.</h1><p className="bank-muted">Reviewed peer inputs · EV / revenue and EV / EBITDA · explicit coverage</p></div><button className="bank-button" disabled={!result || dirty || busy} onClick={() => downloadJson(result, "clear-comparable-valuation.json")}>Export analysis</button></header>
    <nav className="bank-actions" aria-label="Valuation methods"><Link to="/valuation" className="bank-button">Discounted cash flow</Link><strong>Comparable companies</strong></nav>
    <form key={version} className="bank-panel bank-padded" onSubmit={calculate} onChange={() => setDirty(true)}><fieldset disabled={busy}><legend className="bank-form-title">Context & target financials</legend><p className="bank-muted">Use whole units of one currency and the same financial period basis for the target and all peers. Enterprise values must use consistent cash, debt, leases, minority interests and other adjustments. No peer data is invented or automatically selected.</p><div className="bank-form">
      {field("currency", "Currency code", true, { type: "text", defaultValue: initial.currency || "USD", pattern: "[A-Z]{3}", maxLength: 3 })}{field("as_of", "Observation date", true, { type: "date", max: new Date().toISOString().slice(0, 10) })}
      <label className="bank-field"><span>Financial period basis *</span><select name="period_basis" defaultValue={String(initial.period_basis || "LTM")}><option value="LTM">Last twelve months</option><option value="NTM">Next twelve months estimate</option></select></label>
      {field("target_revenue", "Target revenue", false)}{field("target_ebitda", "Target EBITDA", false)}{field("cash", "Cash", true, { min: 0 })}{field("debt", "Debt", true, { min: 0 })}{field("other_claims", "Other debt-like / minority claims", true, { min: 0 })}{field("non_operating_assets", "Other non-operating assets", true, { min: 0 })}{field("diluted_shares", "Diluted shares outstanding", false, { min: 0.000001 })}
      <label className="bank-field bank-span"><span>Target sources, exact period ends & adjustment basis *</span><textarea name="source_note" required maxLength={4000} defaultValue={String(initial.source_note || "")} /></label>
    </div><h2 className="bank-form-title">Peer set</h2><p className="bank-muted">Missing or nonpositive revenue / EBITDA is excluded from that multiple, not treated as zero. Enter zero bridge balances only when confirmed.</p>
    {peers.map((peer, i) => <fieldset className="bank-panel bank-padded" key={i}><legend>Peer {i + 1}</legend><div className="bank-form">{["name", "enterprise_value", "revenue", "ebitda", "source_note"].map(key => <label className="bank-field" key={key}><span>Peer {i + 1} {key.replace(/_/g, " ")}{["name", "enterprise_value", "source_note"].includes(key) ? " *" : ""}</span><input name={`peer_${i}_${key}`} defaultValue={String(peer[key] ?? "")} required={["name", "enterprise_value", "source_note"].includes(key)} type={["name", "source_note"].includes(key) ? "text" : "number"} step="any" maxLength={key === "source_note" ? 4000 : 160} /></label>)}</div></fieldset>)}
    <div className="bank-actions"><button className="bank-button" type="button" disabled={peers.length >= 50} onClick={() => { setPeers([...peers, {}]); setDirty(true); }}>Add peer</button>{peers.length > 1 && <button className="bank-button" type="button" onClick={() => { setPeers(peers.slice(0, -1)); setDirty(true); }}>Remove last peer</button>}<button className="bank-button bank-primary">{busy ? "Calculating…" : "Calculate comparables"}</button></div>{error && <p role="alert" className="bank-error">{error}</p>}</fieldset></form>
    {result && <section className="bank-panel bank-padded" aria-live="polite"><h2>Peer multiples & implied value</h2>{dirty && <p className="bank-error">Inputs changed. Recalculate before saving or exporting.</p>}<div className="bank-table-scroll"><table className="bank-table"><caption>Individual multiples</caption><thead><tr><th>Peer</th><th>EV / revenue</th><th>EV / EBITDA</th></tr></thead><tbody>{result.peers.map(row => <tr key={row.name}><th scope="row">{row.name}</th><td>{row.ev_revenue == null ? "Not meaningful" : `${row.ev_revenue.toFixed(2)}×`}</td><td>{row.ev_ebitda == null ? "Not meaningful" : `${row.ev_ebitda.toFixed(2)}×`}</td></tr>)}</tbody></table></div>
      {result.summaries.map(summary => <div key={summary.metric}><h3 className="bank-form-title">EV / {summary.metric.toUpperCase()} · {summary.included_peers}/{summary.total_peers} peers included</h3><div className="bank-table-scroll"><table className="bank-table"><thead><tr><th>Statistic</th><th>Multiple</th><th>Implied EV</th><th>Equity residual</th><th>Per share</th></tr></thead><tbody>{summary.cases.map(row => <tr key={row.label}><th scope="row">{row.label}</th><td>{row.multiple == null ? "Unavailable" : `${row.multiple.toFixed(2)}×`}</td>{[row.enterprise_value, row.equity_value, row.value_per_share].map((value, i) => <td key={i}>{value == null ? "Unavailable" : money(value, result.inputs.currency)}</td>)}</tr>)}</tbody></table></div></div>)}
      <details className="bank-details"><summary>Methodology & limitations</summary><p>Multiples divide EV by the relevant positive financial metric. Percentiles use linear interpolation at (n−1) × percentile. Target metric × multiple produces EV; the equity bridge adds cash and non-operating assets, then subtracts debt and other claims.</p><ul>{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details></section>}
    <ModelArchive kind="comps" inputs={inputs} disabled={!result || dirty || busy} onLoad={model => { setInitial(model); setPeers(model.peers as Peer[]); setVersion(version + 1); setResult(null); setInputs(null); setDirty(true); setError(""); }} />
  </div>;
}
