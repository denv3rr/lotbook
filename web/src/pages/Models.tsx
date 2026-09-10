import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Calculator } from "lucide-react";
import { apiPost } from "../lib/api";

type Method = "wacc" | "merger" | "lbo" | "bond";
const routes: Record<Method, string> = {
  wacc: "/api/banking/valuation/wacc",
  merger: "/api/banking/valuation/merger",
  lbo: "/api/banking/valuation/lbo",
  bond: "/api/banking/valuation/bond",
};

export default function Models() {
  const [method, setMethod] = useState<Method>("wacc");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const number = (name: string) => Number(data.get(name));
    let payload: Record<string, unknown> = {
      currency: String(data.get("currency") || "USD").toUpperCase(),
      as_of: String(data.get("as_of")),
      source_note: String(data.get("source_note") || "").trim(),
    };
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
      setResult(await apiPost(routes[method], payload));
    } catch (reason) {
      setResult(null);
      setError(reason instanceof Error ? reason.message : "Calculation failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="bank-workspace">
      <header className="bank-heading">
        <div>
          <p className="bank-eyebrow">SCREENING MODELS</p>
          <h1>Assumption-driven banking math.</h1>
          <p className="bank-muted">WACC, merger accretion, LBO MOIC/IRR and bond price/duration. Formula checks, not company evidence.</p>
        </div>
      </header>
      <nav className="bank-actions" aria-label="Valuation methods">
        <Link className="bank-button" to="/valuation">Discounted cash flow</Link>
        <Link className="bank-button" to="/comparables">Comparable companies</Link>
        <strong>More models</strong>
      </nav>
      <form className="bank-panel bank-padded" onSubmit={submit}>
        <fieldset disabled={busy}>
          <legend className="bank-form-title">Model</legend>
          <div className="bank-form">
            <label className="bank-field"><span>Method</span>
              <select name="method" value={method} onChange={(event) => { setMethod(event.target.value as Method); setResult(null); setError(""); }}>
                <option value="wacc">WACC</option>
                <option value="merger">Merger accretion / dilution</option>
                <option value="lbo">LBO MOIC / IRR</option>
                <option value="bond">Bond price / duration</option>
              </select>
            </label>
            <label className="bank-field"><span>Currency *</span><input name="currency" defaultValue="USD" required maxLength={3} /></label>
            <label className="bank-field"><span>Assumption date *</span><input name="as_of" type="date" required max={new Date().toISOString().slice(0, 10)} /></label>
            <label className="bank-field bank-span"><span>Sources and assumption basis *</span><textarea name="source_note" required maxLength={4000} rows={3} /></label>
            {method === "wacc" && ["equity_weight", "debt_weight", "preferred_weight", "cost_of_equity", "pretax_cost_of_debt", "cost_of_preferred", "tax_rate"].map((name) => (
              <label className="bank-field" key={name}><span>{name.replace(/_/g, " ")} (%)</span><input name={name} type="number" step="any" required defaultValue={name === "preferred_weight" || name === "cost_of_preferred" ? "0" : ""} /></label>
            ))}
            {method === "merger" && ["acquirer_net_income", "target_net_income", "synergies_after_tax", "incremental_interest_after_tax", "acquirer_shares", "new_shares"].map((name) => (
              <label className="bank-field" key={name}><span>{name.replace(/_/g, " ")}</span><input name={name} type="number" step="any" required defaultValue={name.includes("shares") || name.includes("income") ? "" : "0"} /></label>
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
              <label className="bank-field"><span>Frequency *</span><input name="frequency" type="number" required defaultValue={2} /></label>
              <label className="bank-field"><span>Day count</span>
                <select name="day_count" defaultValue="30/360">
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
      {result && (
        <section className="bank-panel bank-padded" aria-live="polite">
          <h2>Result</h2>
          <pre className="bank-wrap">{JSON.stringify(result, null, 2)}</pre>
        </section>
      )}
    </div>
  );
}
