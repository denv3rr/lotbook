import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Calculator, Download } from "lucide-react";
import { apiPost } from "../lib/api";
import { downloadJson, money } from "../lib/banking";

type Method = "wacc" | "merger" | "lbo" | "bond";
const routes: Record<Method, string> = {
  wacc: "/api/banking/valuation/wacc",
  merger: "/api/banking/valuation/merger",
  lbo: "/api/banking/valuation/lbo",
  bond: "/api/banking/valuation/bond",
};
const labels: Record<string, string> = {
  equity_weight: "Equity weight (%)",
  debt_weight: "Debt weight (%)",
  preferred_weight: "Preferred weight (%)",
  cost_of_equity: "Cost of equity (%)",
  pretax_cost_of_debt: "Pre-tax cost of debt (%)",
  cost_of_preferred: "Cost of preferred (%)",
  tax_rate: "Tax rate (%)",
  acquirer_net_income: "Acquirer net income",
  target_net_income: "Target net income",
  synergies_after_tax: "After-tax synergies",
  incremental_interest_after_tax: "After-tax incremental interest",
  acquirer_shares: "Acquirer shares",
  new_shares: "New shares issued",
};

type ModelResult = {
  inputs?: { currency?: string; as_of?: string; source_note?: string };
  wacc?: number;
  after_tax_cost_of_debt?: number;
  standalone_eps?: number;
  pro_forma_eps?: number;
  accretion?: number | null;
  moic?: number;
  irr?: number | null;
  price?: number | null;
  macaulay_duration?: number | null;
  modified_duration?: number | null;
  convexity?: number | null;
  warnings?: string[];
  methodology?: Record<string, unknown>;
};

function percent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Unavailable";
  return `${(value * 100).toFixed(2)}%`;
}

export default function Models() {
  const formRef = useRef<HTMLFormElement>(null);
  const [method, setMethod] = useState<Method>("wacc");
  const [currency, setCurrency] = useState("USD");
  const [asOf, setAsOf] = useState("");
  const [sourceNote, setSourceNote] = useState("");
  const [result, setResult] = useState<ModelResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const number = (name: string) => Number(data.get(name));
    let payload: Record<string, unknown> = { currency, as_of: asOf, source_note: sourceNote.trim() };
    if (method === "wacc") {
      payload = {
        ...payload,
        equity_weight: number("equity_weight") / 100,
        debt_weight: number("debt_weight") / 100,
        preferred_weight: number("preferred_weight") / 100,
        cost_of_equity: number("cost_of_equity") / 100,
        pretax_cost_of_debt: number("pretax_cost_of_debt") / 100,
        cost_of_preferred: number("cost_of_preferred") / 100,
        tax_rate: number("tax_rate") / 100,
      };
    } else if (method === "merger") {
      payload = {
        ...payload,
        acquirer_net_income: number("acquirer_net_income"),
        target_net_income: number("target_net_income"),
        synergies_after_tax: number("synergies_after_tax"),
        incremental_interest_after_tax: number("incremental_interest_after_tax"),
        acquirer_shares: number("acquirer_shares"),
        new_shares: number("new_shares"),
      };
    } else if (method === "lbo") {
      payload = { ...payload, sponsor_equity: number("sponsor_equity"), exit_year: number("exit_year"), exit_equity: number("exit_equity") };
    } else {
      payload = {
        ...payload,
        face: number("face"),
        coupon_rate: number("coupon_rate") / 100,
        yield_to_maturity: number("yield_to_maturity") / 100,
        years: number("years"),
        frequency: number("frequency"),
        day_count: String(data.get("day_count")),
      };
    }
    try {
      setResult(await apiPost<ModelResult>(routes[method], payload));
      setDirty(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Calculation failed.");
    } finally {
      setBusy(false);
    }
  }

  const figures = result ? (
    method === "wacc" ? [
      ["WACC", percent(result.wacc)],
      ["After-tax cost of debt", percent(result.after_tax_cost_of_debt)],
    ] : method === "merger" ? [
      ["Standalone EPS", money(result.standalone_eps, result.inputs?.currency || currency)],
      ["Pro forma EPS", money(result.pro_forma_eps, result.inputs?.currency || currency)],
      ["Accretion / dilution", percent(result.accretion)],
    ] : method === "lbo" ? [
      ["MOIC", result.moic == null ? "Unavailable" : result.moic.toFixed(2)],
      ["IRR", percent(result.irr)],
    ] : [
      ["Price", money(result.price, result.inputs?.currency || currency)],
      ["Macaulay duration", result.macaulay_duration == null ? "Unavailable" : result.macaulay_duration.toFixed(3)],
      ["Modified duration", result.modified_duration == null ? "Unavailable" : result.modified_duration.toFixed(3)],
      ["Convexity", result.convexity == null ? "Unavailable" : result.convexity.toFixed(3)],
    ]
  ) : [];

  return (
    <div className="bank-workspace">
      <header className="bank-heading">
        <div>
          <p className="bank-eyebrow">SCREENING MODELS</p>
          <h1>Assumption-driven banking math.</h1>
          <p className="bank-muted">WACC, merger accretion, LBO MOIC/IRR and bond price/duration. Formula checks, not company evidence.</p>
        </div>
        <button className="bank-button" disabled={!result || dirty || busy} onClick={() => downloadJson(result, `clear-${method}.json`)}><Download size={16} /> Export</button>
      </header>
      <nav className="bank-actions" aria-label="Valuation methods">
        <Link className="bank-button" to="/valuation">Discounted cash flow</Link>
        <Link className="bank-button" to="/comparables">Comparable companies</Link>
        <strong>More models</strong>
      </nav>
      <div className="bank-valuation-grid">
        <form ref={formRef} className="bank-panel bank-padded" onSubmit={submit} onChange={() => setDirty(true)}>
          <fieldset disabled={busy}>
            <legend className="bank-form-title">Model</legend>
            <div className="bank-form">
              <label className="bank-field"><span>Method</span>
                <select name="method" aria-label="Model method" value={method} onChange={(event) => { setMethod(event.target.value as Method); setError(""); }}>
                  <option value="wacc">WACC</option>
                  <option value="merger">Merger accretion / dilution</option>
                  <option value="lbo">LBO MOIC / IRR</option>
                  <option value="bond">Bond price / duration</option>
                </select>
              </label>
              <label className="bank-field"><span>Currency *</span><input name="currency" value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} required maxLength={3} /></label>
              <label className="bank-field"><span>Assumption date *</span><input name="as_of" type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} required max={new Date().toISOString().slice(0, 10)} /></label>
              <label className="bank-field bank-span"><span>Sources and assumption basis *</span><textarea name="source_note" value={sourceNote} onChange={(event) => setSourceNote(event.target.value)} required maxLength={4000} rows={3} /></label>
              {method === "wacc" && ["equity_weight", "debt_weight", "preferred_weight", "cost_of_equity", "pretax_cost_of_debt", "cost_of_preferred", "tax_rate"].map((name) => (
                <label className="bank-field" key={name}><span>{labels[name]}</span><input name={name} type="number" step="any" required defaultValue={name === "preferred_weight" || name === "cost_of_preferred" ? "0" : ""} /></label>
              ))}
              {method === "merger" && ["acquirer_net_income", "target_net_income", "synergies_after_tax", "incremental_interest_after_tax", "acquirer_shares", "new_shares"].map((name) => (
                <label className="bank-field" key={name}><span>{labels[name]}</span><input name={name} type="number" step="any" required defaultValue={name.includes("shares") || name.includes("income") ? "" : "0"} /></label>
              ))}
              {method === "lbo" && <>
                <label className="bank-field"><span>Sponsor equity *</span><input name="sponsor_equity" type="number" step="any" required min="0.000001" /></label>
                <label className="bank-field"><span>Exit year *</span><input name="exit_year" type="number" required min={1} max={20} defaultValue={5} /></label>
                <label className="bank-field"><span>Exit equity *</span><input name="exit_equity" type="number" step="any" required /></label>
              </>}
              {method === "bond" && <>
                <label className="bank-field"><span>Face *</span><input name="face" type="number" step="any" required /></label>
                <label className="bank-field"><span>Coupon % *</span><input name="coupon_rate" type="number" step="any" required /></label>
                <label className="bank-field"><span>YTM % *</span><input name="yield_to_maturity" type="number" step="any" required /></label>
                <label className="bank-field"><span>Years *</span><input name="years" type="number" step="any" required /></label>
                <label className="bank-field"><span>Payments per year *</span><input name="frequency" type="number" required defaultValue={2} /></label>
                <label className="bank-field"><span>Day count</span>
                  <select name="day_count" defaultValue="30/360" aria-label="Day count">
                    <option>30/360</option>
                    <option>ACT/365</option>
                    <option>ACT/ACT</option>
                  </select>
                </label>
              </>}
            </div>
            {error && <p role="alert" className="bank-error">{error}</p>}
            <button className="bank-button bank-primary" type="submit"><Calculator size={16} />{busy ? "Calculating…" : "Calculate"}</button>
          </fieldset>
        </form>
        <section className="bank-panel bank-padded" aria-live="polite">
          {!result ? (
            <div className="bank-empty"><Calculator size={30} /><h2>Results appear here.</h2><p>Enter assumptions and calculate. Currency, date and source stay in place when you switch methods.</p></div>
          ) : (
            <>
              {dirty && <p className="bank-error">Inputs have changed. Recalculate to update these results and enable export.</p>}
              <p className="bank-eyebrow">ASSUMPTION-BASED SCREEN · {result.inputs?.currency || currency}</p>
              <h2>Results</h2>
              <p className="bank-muted">As of {result.inputs?.as_of || asOf}. Formula checks do not verify company evidence.</p>
              <div className="bank-stats bank-stats-two">
                {figures.map(([label, value]) => <div className="bank-stat" key={label}><span>{label}</span><strong className="bank-value">{value}</strong></div>)}
              </div>
              <details className="bank-details"><summary>Methodology, sources, and limitations</summary><p>{result.inputs?.source_note || sourceNote}</p><ul>{(result.warnings || []).map(warning => <li key={warning}>{warning}</li>)}</ul></details>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
