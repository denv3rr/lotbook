import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ModelArchive } from "../components/banking/ModelArchive";
import { Download, Plus, Calculator } from "lucide-react";
import { apiPost } from "../lib/api";
import { downloadJson, money } from "../lib/banking";

type DcfResult = { inputs: { currency: string; as_of: string; source_note: string }; enterprise_value: number; equity_value: number; value_per_share: number | null; forecast_present_value: number; pv_terminal_value: number; terminal_value_share: number | null; forecast: { year: number; cash_flow: number; discount_factor: number; present_value: number }[]; sensitivity: { wacc_values: number[]; terminal_growth_values: number[]; enterprise_values: (number | null)[][] }; warnings: string[]; methodology: Record<string, unknown> };
export default function Valuation() {
  const formRef = useRef<HTMLFormElement>(null);
  const [modelInputs, setModelInputs] = useState<Record<string, unknown> | null>(null);
  const [years, setYears] = useState([""]);
  const [result, setResult] = useState<DcfResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const input = (name: string, caption: string, options: Record<string, unknown> = {}) => <label className="bank-field"><span>{caption}</span><input name={name} type="number" step="any" required {...options} /></label>;
  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const entries = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = { cash_flows: years.map(Number) };
    for (const name of ["wacc", "terminal_growth", "cash", "debt", "other_claims", "non_operating_assets"]) payload[name] = Number(entries.get(name));
    payload.wacc = Number(payload.wacc) / 100; payload.terminal_growth = Number(payload.terminal_growth) / 100;
    payload.diluted_shares = entries.get("diluted_shares") ? Number(entries.get("diluted_shares")) : null;
    for (const name of ["currency", "as_of", "source_note"]) payload[name] = String(entries.get(name)).trim();
    try { setResult(await apiPost<DcfResult>("/api/banking/valuation/dcf", payload)); setModelInputs(payload); setDirty(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Calculation failed."); }
    finally { setBusy(false); }
  }
  return <div className="bank-workspace"><header className="bank-heading"><div><p className="bank-eyebrow">VALUATION WORKSPACE</p><h1>Understand the value drivers.</h1><p className="bank-muted">Annual unlevered cash flows · end-of-year discounting · perpetual-growth terminal value</p></div><button className="bank-button" disabled={!result || dirty || busy} onClick={() => downloadJson(result, "clear-dcf-valuation.json")}><Download size={16} /> Export valuation</button></header>
    <nav className="bank-actions" aria-label="Valuation methods"><strong>Discounted cash flow</strong><Link className="bank-button" to="/comparables">Comparable companies</Link><Link className="bank-button" to="/models">More models</Link></nav><div className="bank-valuation-grid"><form ref={formRef} className="bank-panel bank-padded" onSubmit={calculate} onChange={() => setDirty(true)}><fieldset disabled={busy}><legend className="bank-form-title">1. Model context</legend><div className="bank-form">{input("currency", "Currency code *", { type: "text", defaultValue: "USD", pattern: "[A-Z]{3}", maxLength: 3 })}{input("as_of", "Valuation date *", { type: "date", max: new Date().toISOString().slice(0, 10) })}<label className="bank-field bank-span"><span>Sources and assumption basis *</span><textarea name="source_note" required maxLength={4000} rows={3} /></label></div>
      <h2 className="bank-form-title">2. Forecast cash flows</h2><p className="bank-muted">Enter annual free cash flow to the firm (FCFF), after reinvestment and before debt payments. Use whole currency units throughout, not millions. Negative forecast cash flow is allowed.</p><div className="bank-form">{years.map((value, index) => <label className="bank-field" key={index}><span>Year {index + 1} FCFF *</span><input required type="number" step="any" value={value} onChange={event => setYears(previous => previous.map((entry, i) => i === index ? event.target.value : entry))} /></label>)}</div><div className="bank-actions"><button className="bank-button" type="button" disabled={years.length >= 20} onClick={() => { setYears([...years, ""]); setDirty(true); }}><Plus size={15} /> Add year</button>{years.length > 1 && <button className="bank-button" type="button" onClick={() => { setYears(years.slice(0, -1)); setDirty(true); }}>Remove last year</button>}</div>
      <h2 className="bank-form-title">3. Discount rate & equity bridge</h2><div className="bank-form">{input("wacc", "WACC (%) *", { min: 0.000001, max: 100 })}{input("terminal_growth", "Terminal growth (%) *", { min: -99.999, max: 20 })}{input("cash", "Cash *", { min: 0 })}{input("debt", "Debt *", { min: 0 })}{input("non_operating_assets", "Other non-operating assets *", { min: 0 })}{input("other_claims", "Other debt-like / minority claims *", { min: 0 })}{input("diluted_shares", "Diluted shares outstanding", { min: 0.000001, required: false })}</div><p className="bank-muted">Enter zero only for a confirmed zero balance. WACC must exceed terminal growth. Share count is optional; use actual shares, not millions.</p>
      {error && <p role="alert" className="bank-error">{error}</p>}<button className="bank-button bank-primary" type="submit"><Calculator size={16} />{busy ? "Calculating…" : "Calculate valuation"}</button>
    </fieldset></form><section className="bank-panel bank-padded" aria-live="polite">
      {!result ? <div className="bank-empty"><Calculator size={30} /><h2>Your valuation will appear here.</h2><p>Supply your forecast and assumptions to see discounted cash flows, the equity bridge, and sensitivity to WACC and growth.</p></div> : <>
        {dirty && <p className="bank-error">Inputs have changed. Recalculate to update these results and enable export.</p>}<p className="bank-eyebrow">ASSUMPTION-BASED VALUATION · {result.inputs.currency}</p><h2>Valuation and sensitivity</h2><p className="bank-muted">As of {result.inputs.as_of}. Calculation checks do not verify your sources or assumptions.</p><div className="bank-stats bank-stats-two">{[["Enterprise value", result.enterprise_value], ["Equity residual", result.equity_value]].map(([label, value]) => <div className="bank-stat" key={String(label)}><span>{label}</span><strong className="bank-value">{money(value, result.inputs.currency)}</strong></div>)}</div><p>Value per diluted share: <strong>{result.value_per_share == null ? "Unavailable — no share count" : money(result.value_per_share, result.inputs.currency)}</strong></p><p className="bank-muted">Terminal value contribution: {result.terminal_value_share == null ? "Not meaningful for this enterprise value" : `${(result.terminal_value_share * 100).toFixed(1)}%`}</p>
        <div className="bank-table-scroll"><table className="bank-table"><caption>Annual cash flow discounting</caption><thead><tr><th>Year</th><th>FCFF</th><th>PV factor</th><th>Present value</th></tr></thead><tbody>{result.forecast.map(row => <tr key={row.year}><th scope="row">{row.year}</th><td>{money(row.cash_flow, result.inputs.currency)}</td><td>{row.discount_factor.toFixed(4)}</td><td>{money(row.present_value, result.inputs.currency)}</td></tr>)}</tbody><tfoot><tr><th colSpan={3}>PV of forecast</th><td>{money(result.forecast_present_value, result.inputs.currency)}</td></tr><tr><th colSpan={3}>PV of terminal value</th><td>{money(result.pv_terminal_value, result.inputs.currency)}</td></tr></tfoot></table></div>
        <h3 className="bank-form-title">Enterprise value sensitivity</h3><p className="bank-muted">Rows: WACC. Columns: terminal growth. Unavailable cells fall outside the model domain.</p><div className="bank-table-scroll"><table className="bank-table bank-sensitivity"><thead><tr><th>WACC / growth</th>{result.sensitivity.terminal_growth_values.map(value => <th key={value}>{(value * 100).toFixed(2)}%</th>)}</tr></thead><tbody>{result.sensitivity.enterprise_values.map((row, index) => <tr key={index}><th scope="row">{(result.sensitivity.wacc_values[index] * 100).toFixed(2)}%</th>{row.map((value, i) => <td key={i}>{value == null ? "Unavailable" : money(value, result.inputs.currency)}</td>)}</tr>)}</tbody></table></div>
        <details className="bank-details"><summary>Methodology, sources, and limitations</summary><p>{result.inputs.source_note}</p><p>EV = sum of FCFF discounted at WACC + discounted terminal value. Terminal value = final FCFF × (1 + growth) / (WACC − growth). Equity residual adds cash and non-operating assets and subtracts debt and other claims.</p><ul>{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>
      </>}
    </section></div><ModelArchive kind="dcf" inputs={modelInputs} disabled={dirty || busy || !result} onLoad={inputs => {
      setYears((inputs.cash_flows as number[]).map(String));
      for (const [name, value] of Object.entries(inputs)) {
        const control = formRef.current?.elements.namedItem(name);
        if (control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement) control.value = value == null ? "" : String(["wacc", "terminal_growth"].includes(name) ? Number(value) * 100 : value);
      }
      setResult(null); setModelInputs(null); setDirty(true); setError(""); formRef.current?.scrollIntoView({ block: "start" });
    }} /></div>;
}
