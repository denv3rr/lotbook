import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AreaSparkline, DistributionBars } from "../components/ui/Charts";
import { Card } from "../components/ui/Card";
import { Collapsible } from "../components/ui/Collapsible";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { KpiCard } from "../components/ui/KpiCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { Surface3D } from "../components/ui/Surface3D";
import { VisualizationGuide } from "../components/ui/VisualizationGuide";
import { apiGet, apiPatch, apiPost, invalidateApiCache, useApi } from "../lib/api";
import { PositionsBook } from "../components/clients/PositionsBook";

type ClientSummary = {
  client_id: string;
  name: string;
  risk_profile?: string;
  accounts_count: number;
  holdings_count: number;
  reporting_currency?: string;
};

type ClientIndex = {
  clients: ClientSummary[];
};

type LotEntry = {
  qty: number;
  basis: number;
  timestamp: string;
  source?: string;
  kind?: string;
};

type AccountDetail = {
  account_id: string;
  account_name: string;
  account_type?: string;
  holdings_count: number;
  manual_value: number;
  tags: string[];
  holdings: Record<string, number>;
  lots?: Record<string, LotEntry[]>;
  manual_holdings: { name?: string; total_value?: number }[];
  tax_settings: Record<string, string | number | boolean>;
  custodian?: string | null;
  ownership_type?: string | null;
};

type ClientDetail = ClientSummary & {
  tax_profile: Record<string, string | number | boolean>;
  accounts: AccountDetail[];
};

type HistoryPoint = {
  ts: number | null;
  value: number;
};

type RiskPayload = {
  error?: string;
  metrics?: Record<string, number>;
  risk_profile?: string;
  meta?: string;
  returns?: { ts: number | null; value: number }[];
  benchmark_returns?: { ts: number | null; value: number }[];
  distribution?: { bin_start: number; bin_end: number; count: number }[];
};

type RegimePayload = {
  error?: string;
  error_detail?: string;
  samples?: number;
  transition_matrix?: number[][];
  state_probs?: Record<string, number>;
  evolution?: { series?: Record<string, number>[] };
  window?: { interval?: string; series?: HistoryPoint[] };
};

type SurfacePayload = {
  z: number[][];
  x?: number[];
  y?: number[];
  axis?: {
    x_label?: string;
    y_label?: string;
    z_label?: string;
    x_unit?: string;
    y_unit?: string;
    z_unit?: string;
  };
};

type PatternPayload = {
  error?: string;
  entropy?: number | null;
  perm_entropy?: number | null;
  hurst?: number | null;
  change_points?: number[];
  motifs?: { window: string; distance: number }[];
  vol_forecast?: number[];
  spectrum?: { freq: number; power: number }[];
  wave_surface?: SurfacePayload;
  fft_surface?: SurfacePayload;
};

type DashboardPayload = {
  client: ClientSummary;
  account?: AccountDetail;
  interval: string;
  totals: {
    market_value: number;
    manual_value: number | null;
    total_value: number | null;
    holdings_count: number;
    manual_count: number;
  };
  holdings: Array<{
    ticker: string;
    name?: string;
    sector?: string;
    quantity: number;
    price: number;
    market_value: number;
    change: number;
    pct: number;
    history?: number[];
  }>;
  manual_holdings: { name?: string; total_value?: number }[];
  history: HistoryPoint[];
  risk: RiskPayload;
  regime: RegimePayload;
  diagnostics?: {
    sectors: { sector: string; value: number; pct: number }[];
    hhi: number | null;
    gainers: { ticker: string; pct: number; change: number }[];
    losers: { ticker: string; pct: number; change: number }[];
  };
  market_snapshot?: {
    source?: string;
    label?: string;
    cache?: string;
  };
  warnings: string[];
};

type AccountWriteResponse = {
  client: ClientDetail;
  account: AccountDetail;
};

const intervals = ["1W", "1M", "3M", "6M", "1Y"];

const metricDefinitions: Record<string, {
  label: string;
  technical: string;
  description: string;
  unit: "percent" | "ratio";
}> = {
  mean_annual: {
    label: "Expected Annual Return",
    technical: "Annualized mean return (μ)",
    description: "The average return projected to one year from the available observations.",
    unit: "percent",
  },
  vol_annual: {
    label: "Portfolio Risk",
    technical: "Annualized volatility (σ)",
    description: "How widely returns tend to fluctuate around their average.",
    unit: "percent",
  },
  sharpe: {
    label: "Risk-Adjusted Return",
    technical: "Sharpe ratio",
    description: "Excess return earned per unit of total volatility.",
    unit: "ratio",
  },
  sortino: {
    label: "Downside Risk-Adjusted Return",
    technical: "Sortino ratio",
    description: "Excess return earned per unit of downside volatility.",
    unit: "ratio",
  },
  beta: {
    label: "Market Sensitivity",
    technical: "Beta (β)",
    description: "How strongly the portfolio has moved relative to its benchmark.",
    unit: "ratio",
  },
  alpha_annual: {
    label: "Benchmark-Adjusted Return",
    technical: "Annualized alpha (α)",
    description: "Annualized return not explained by the portfolio's measured benchmark sensitivity.",
    unit: "percent",
  },
  r_squared: {
    label: "Benchmark Fit",
    technical: "R-squared (R²)",
    description: "The share of observed return variation explained by the benchmark relationship.",
    unit: "percent",
  },
  max_drawdown: {
    label: "Largest Peak-to-Trough Decline",
    technical: "Maximum drawdown",
    description: "The largest observed decline from a prior portfolio peak.",
    unit: "percent",
  },
  var_95: {
    label: "One-Period Loss Threshold",
    technical: "Value at Risk (VaR), 95%",
    description: "The historical one-period return threshold exceeded by the worst 5% of observations.",
    unit: "percent",
  },
  cvar_95: {
    label: "Average Severe Loss",
    technical: "Conditional VaR (CVaR), 95%",
    description: "The average return among observations beyond the 95% Value at Risk threshold.",
    unit: "percent",
  },
};

export default function Clients() {
  const [searchParams] = useSearchParams();
  const {
    data: index,
    error: indexError,
    loading: indexLoading,
    refresh: refreshIndex
  } = useApi<ClientIndex>("/api/clients", { interval: 60000 });
  const rows = index?.clients ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("client"));
  const [detail, setDetail] = useState<ClientDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [interval, setInterval] = useState("1M");
  const [selectedAccount, setSelectedAccount] = useState<string>("portfolio");  
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);    
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [patterns, setPatterns] = useState<PatternPayload | null>(null);        
  const [patternsError, setPatternsError] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const [riskOpen, setRiskOpen] = useState(true);
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [regimeOpen, setRegimeOpen] = useState(false);
  const [patternOpen, setPatternOpen] = useState(false);
  const [holdingsOpen, setHoldingsOpen] = useState(true);
  const [lotsOpen, setLotsOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [dashboardEpoch, setDashboardEpoch] = useState(0);
  const dashboardPathRef = useRef("");
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [accountFormOpen, setAccountFormOpen] = useState(false);
  const [accountEditOpen, setAccountEditOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSaving, setFormSaving] = useState(false);

  const [clientForm, setClientForm] = useState({
    name: "",
    risk_profile: "",
    residency_country: "",
    tax_country: "",
    reporting_currency: "USD",
    treaty_country: "",
    tax_id: ""
  });
  const [accountForm, setAccountForm] = useState({
    account_name: "",
    account_type: "Taxable",
    ownership_type: "Individual",
    custodian: "",
    tags: ""
  });
  const [accountEditForm, setAccountEditForm] = useState({
    account_name: "",
    account_type: "",
    ownership_type: "",
    custodian: "",
    tags: ""
  });

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setDetailError(null);
    if (!selectedId) {
      return;
    }
    apiGet<ClientDetail>(`/api/clients/${encodeURIComponent(selectedId)}`, 0, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setDetail(payload);
        setDetailError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setDetail(null);
        setDetailError(err instanceof Error ? err.message : "Client detail failed.");
      });
    return () => controller.abort();
  }, [selectedId]);

  useEffect(() => {
    if (formMode !== "edit" || !detail) return;
    setClientForm({
      name: detail.name || "",
      risk_profile: detail.risk_profile || "",
      residency_country: String(detail.tax_profile?.residency_country || ""),
      tax_country: String(detail.tax_profile?.tax_country || ""),
      reporting_currency: String(detail.tax_profile?.reporting_currency || "USD"),
      treaty_country: String(detail.tax_profile?.treaty_country || ""),
      tax_id: String(detail.tax_profile?.tax_id || "")
    });
  }, [formMode, detail]);

  useEffect(() => {
    if (!accountEditOpen || !detail || selectedAccount === "portfolio") return;
    const account = detail.accounts.find((item) => item.account_id === selectedAccount);
    if (!account) return;
    setAccountEditForm({
      account_name: account.account_name || "",
      account_type: account.account_type || "",
      ownership_type: account.ownership_type || "",
      custodian: account.custodian || "",
      tags: account.tags?.join(", ") || ""
    });
  }, [accountEditOpen, detail, selectedAccount]);

  useEffect(() => {
    if (selectedAccount === "portfolio") {
      setAccountEditOpen(false);
    }
  }, [selectedAccount]);

  useEffect(() => {
    const controller = new AbortController();
    setDashboardError(null);
    setDashboardLoading(Boolean(selectedId));
    if (!selectedId) return;
    const path =
      selectedAccount === "portfolio"
        ? `/api/clients/${encodeURIComponent(selectedId)}/dashboard?interval=${encodeURIComponent(interval)}`
        : `/api/clients/${encodeURIComponent(selectedId)}/accounts/${encodeURIComponent(
            selectedAccount
          )}/dashboard?interval=${encodeURIComponent(interval)}`;
    if (dashboardPathRef.current !== path) {
      setDashboard(null);
      dashboardPathRef.current = path;
    }
    apiGet<DashboardPayload>(path, 20000, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setDashboard(payload);
        setDashboardError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setDashboard(null);
        setDashboardError(err instanceof Error ? err.message : "Dashboard failed.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setDashboardLoading(false);
      });
    return () => controller.abort();
  }, [selectedId, selectedAccount, interval, dashboardEpoch]);

  useEffect(() => {
    const controller = new AbortController();
    setPatterns(null);
    setPatternsError(null);
    if (!selectedId || !patternOpen) return;
    const path =
      selectedAccount === "portfolio"
        ? `/api/clients/${encodeURIComponent(selectedId)}/patterns?interval=${encodeURIComponent(interval)}`
        : `/api/clients/${encodeURIComponent(selectedId)}/accounts/${encodeURIComponent(
            selectedAccount
          )}/patterns?interval=${encodeURIComponent(interval)}`;
    apiGet<PatternPayload>(path, 0, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setPatterns(payload);
        setPatternsError(null);
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setPatterns(null);
        setPatternsError(err instanceof Error ? err.message : "Pattern analysis failed.");
      });
    return () => controller.abort();
  }, [selectedId, selectedAccount, interval, patternOpen, dashboardEpoch]);

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const needle = query.trim().toLowerCase();
    return rows.filter(
      (client) =>
        client.name.toLowerCase().includes(needle) ||
        client.client_id.toLowerCase().includes(needle) ||
        (client.risk_profile || "").toLowerCase().includes(needle)
    );
  }, [rows, query]);

  const accountOptions = useMemo(() => {
    if (!detail?.accounts?.length) return [];
    return detail.accounts.map((account) => ({
      value: account.account_id,
      label: `${account.account_name} (${account.account_id.slice(0, 6)})`
    }));
  }, [detail]);

  const summary = useMemo(() => {
    const accounts = rows.reduce((acc, client) => acc + (client.accounts_count || 0), 0);
    const holdings = rows.reduce((acc, client) => acc + (client.holdings_count || 0), 0);
    return {
      clients: rows.length,
      accounts,
      holdings
    };
  }, [rows]);

  const profileRows = useMemo(() => {
    const entries = Object.entries(detail?.tax_profile || {});
    if (!entries.length) {
      return [["Tax Profile", "No tax profile configured."]];
    }
    return entries.map(([key, value]) => [key, String(value)]);
  }, [detail]);

  const selectedAccountDetail = useMemo(() => {
    if (!detail?.accounts?.length || selectedAccount === "portfolio") return null;
    return detail.accounts.find((account) => account.account_id === selectedAccount) || null;
  }, [detail, selectedAccount]);

  const accountRows = useMemo(() => {
    if (!detail?.accounts?.length) return [];
    return detail.accounts.map((account) => ({
      id: account.account_id,
      name: account.account_name,
      type: account.account_type || "N/A",
      custodian: account.custodian || "N/A",
      ownership: account.ownership_type || "N/A",
      tags: account.tags?.length ? account.tags.join(", ") : "None",
      taxKeys: Object.keys(account.tax_settings || {}).length
    }));
  }, [detail]);

  const activeTotals = dashboard?.totals;
  const activeHoldings = dashboard?.holdings || [];
  const riskMetrics = dashboard?.risk?.metrics || {};
  const riskMetricRows = Object.keys(metricDefinitions)
    .map((key) => {
      if (!(key in riskMetrics)) return null;
      const value = Number(riskMetrics[key]);
      if (!Number.isFinite(value)) return null;
      return {
        key,
        ...metricDefinitions[key],
        value,
        displayValue:
          metricDefinitions[key].unit === "percent"
            ? `${(value * 100).toFixed(2)}%`
            : value.toFixed(3)
      };
    })
    .filter(Boolean) as Array<{
      key: string;
      label: string;
      technical: string;
      description: string;
      unit: "percent" | "ratio";
      value: number;
      displayValue: string;
    }>;
  const authHint = "Check CLEAR_WEB_API_KEY + localStorage clear_api_key.";
  const errorMessages = [
    indexError
      ? `Client index failed: ${indexError}${
          indexError.includes("401") || indexError.includes("403") ? ` (${authHint})` : ""
        }`
      : null,
    detailError ? `Client detail failed: ${detailError}` : null,
    dashboardError ? `Dashboard failed: ${dashboardError}` : null,
    patternsError ? `Patterns failed: ${patternsError}` : null,
    formError ? `Client workflow: ${formError}` : null
  ].filter(Boolean) as string[];

  const resetClientForm = () => {
    setClientForm({
      name: "",
      risk_profile: "",
      residency_country: "",
      tax_country: "",
      reporting_currency: "USD",
      treaty_country: "",
      tax_id: ""
    });
  };

  const resetAccountForm = () => {
    setAccountForm({
      account_name: "",
      account_type: "Taxable",
      ownership_type: "Individual",
      custodian: "",
      tags: ""
    });
  };

  const resetAccountEditForm = () => {
    setAccountEditForm({
      account_name: "",
      account_type: "",
      ownership_type: "",
      custodian: "",
      tags: ""
    });
  };

  const handleCreateClient = async (event: FormEvent) => {
    event.preventDefault();
    setFormSaving(true);
    setFormError(null);
    try {
      const payload = {
        name: clientForm.name.trim(),
        risk_profile: clientForm.risk_profile.trim() || undefined,
        tax_profile: {
          residency_country: clientForm.residency_country.trim(),
          tax_country: clientForm.tax_country.trim(),
          reporting_currency: clientForm.reporting_currency.trim() || "USD",
          treaty_country: clientForm.treaty_country.trim(),
          tax_id: clientForm.tax_id.trim()
        }
      };
      const created = await apiPost<ClientDetail>("/api/clients", payload);
      await refreshIndex();
      setSelectedId(created.client_id);
      setSelectedAccount("portfolio");
      setFormMode(null);
      resetClientForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create client.");
    } finally {
      setFormSaving(false);
    }
  };

  const handleUpdateClient = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId) return;
    setFormSaving(true);
    setFormError(null);
    try {
      const payload = {
        name: clientForm.name.trim(),
        risk_profile: clientForm.risk_profile.trim() || undefined,
        tax_profile: {
          residency_country: clientForm.residency_country.trim(),
          tax_country: clientForm.tax_country.trim(),
          reporting_currency: clientForm.reporting_currency.trim() || "USD",
          treaty_country: clientForm.treaty_country.trim(),
          tax_id: clientForm.tax_id.trim()
        }
      };
      const updated = await apiPatch<ClientDetail>(
        `/api/clients/${encodeURIComponent(selectedId)}`,
        payload
      );
      setDetail(updated);
      await refreshIndex();
      setFormMode(null);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to update client.");
    } finally {
      setFormSaving(false);
    }
  };

  const handleAddAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId) return;
    setFormSaving(true);
    setFormError(null);
    try {
      const tags = accountForm.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const payload = {
        account_name: accountForm.account_name.trim(),
        account_type: accountForm.account_type.trim(),
        ownership_type: accountForm.ownership_type.trim(),
        custodian: accountForm.custodian.trim(),
        tags
      };
      const updated = await apiPost<AccountWriteResponse>(
        `/api/clients/${encodeURIComponent(selectedId)}/accounts`,
        payload
      );
      setDetail(updated.client);
      setSelectedAccount(updated.account.account_id);
      setAccountFormOpen(false);
      resetAccountForm();
      await refreshIndex();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to add account.");
    } finally {
      setFormSaving(false);
    }
  };

  const handleUpdateAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId || selectedAccount === "portfolio") return;
    setFormSaving(true);
    setFormError(null);
    try {
      const tags = accountEditForm.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const payload = {
        account_name: accountEditForm.account_name.trim(),
        account_type: accountEditForm.account_type.trim(),
        ownership_type: accountEditForm.ownership_type.trim(),
        custodian: accountEditForm.custodian.trim(),
        tags
      };
      const updated = await apiPatch<AccountWriteResponse>(
        `/api/clients/${encodeURIComponent(selectedId)}/accounts/${encodeURIComponent(selectedAccount)}`,
        payload
      );
      setDetail(updated.client);
      setAccountEditOpen(false);
      resetAccountEditForm();
      await refreshIndex();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to update account.");
    } finally {
      setFormSaving(false);
    }
  };

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader
        label="CLIENTS"
        title="Portfolio Command Center"
        right={
          selectedId
            ? `${detail?.name || "Loading client"}`
            : `${summary.clients} clients`
        }
      />
      <ErrorBanner messages={errorMessages} onRetry={refreshIndex} />
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-6">
        <div className="space-y-3 text-sm text-slate-300">
          <div className="flex items-center justify-between">
            <label htmlFor="client-search" className="text-xs text-slate-300">
              Search
            </label>
            <button
              type="button"
              onClick={() => {
                setFormMode("create");
                setAccountFormOpen(false);
                resetClientForm();
                setFormError(null);
              }}
              className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-100 hover:text-green-500"
            >
              New Client
            </button>
          </div>
          <input
            id="client-search"
            name="client-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="w-full rounded-xl bg-slate-950/60 border border-slate-700 px-4 py-2 text-sm text-slate-100"
            placeholder="Name, ID, risk profile..."
          />
          {filtered.length === 0 ? (
            <p>{indexLoading ? "Loading client profiles..." : "No client profiles loaded."}</p>
          ) : (
            filtered.map((client) => (
              <button
                key={client.client_id}
                onClick={() => {
                  setSelectedId(client.client_id);
                  setSelectedAccount("portfolio");
                }}
                className={`w-full rounded-xl border px-4 py-3 text-left ${
                  selectedId === client.client_id
                    ? "border-green-400/60 text-green-100"
                    : "border-slate-700 text-slate-100"
                }`}
              >
                <p className="text-slate-100 font-medium">{client.name}</p>
                <p className="text-xs text-slate-300">{client.client_id}</p>
                <p className="text-xs text-green-300 mt-1">
                  {client.risk_profile || "Risk profile unknown"}
                </p>
              </button>
            ))
          )}
        </div>
        <div className="lg:col-span-3 space-y-5">
          {formMode === "create" ? (
            <div className="rounded-2xl border border-slate-800/60 bg-ink-950/40 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Create Client</p>
                  <p className="text-sm text-slate-100 font-medium">New Client Profile</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormMode(null)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
              </div>
              <form className="mt-4 space-y-4" onSubmit={handleCreateClient}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="client-name">
                      Client Name
                    </label>
                    <input
                      id="client-name"
                      value={clientForm.name}
                      onChange={(event) => setClientForm({ ...clientForm, name: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Atlas Capital"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="risk-profile">
                      Risk Profile
                    </label>
                    <input
                      id="risk-profile"
                      value={clientForm.risk_profile}
                      onChange={(event) => setClientForm({ ...clientForm, risk_profile: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Balanced"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="reporting-currency">
                      Reporting Currency
                    </label>
                    <input
                      id="reporting-currency"
                      value={clientForm.reporting_currency}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, reporting_currency: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="USD"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="residency-country">
                      Residency Country
                    </label>
                    <input
                      id="residency-country"
                      value={clientForm.residency_country}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, residency_country: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="United States"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="tax-country">
                      Tax Country
                    </label>
                    <input
                      id="tax-country"
                      value={clientForm.tax_country}
                      onChange={(event) => setClientForm({ ...clientForm, tax_country: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="United States"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="treaty-country">
                      Treaty Country
                    </label>
                    <input
                      id="treaty-country"
                      value={clientForm.treaty_country}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, treaty_country: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Canada"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="tax-id">
                      Tax ID
                    </label>
                    <input
                      id="tax-id"
                      value={clientForm.tax_id}
                      onChange={(event) => setClientForm({ ...clientForm, tax_id: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Optional"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setFormMode(null)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={formSaving}
                    className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200"
                  >
                    {formSaving ? "Saving..." : "Create Client"}
                  </button>
                </div>
              </form>
            </div>
          ) : null}
          {formMode === "edit" && selectedId ? (
            <div className="rounded-2xl border border-slate-800/60 bg-ink-950/40 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Edit Client</p>
                  <p className="text-sm text-slate-100 font-medium">Update Client Profile</p>
                </div>
                <button
                  type="button"
                  onClick={() => setFormMode(null)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
              </div>
              <form className="mt-4 space-y-4" onSubmit={handleUpdateClient}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-client-name">
                      Client Name
                    </label>
                    <input
                      id="edit-client-name"
                      value={clientForm.name}
                      onChange={(event) => setClientForm({ ...clientForm, name: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-risk-profile">
                      Risk Profile
                    </label>
                    <input
                      id="edit-risk-profile"
                      value={clientForm.risk_profile}
                      onChange={(event) => setClientForm({ ...clientForm, risk_profile: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-reporting-currency">
                      Reporting Currency
                    </label>
                    <input
                      id="edit-reporting-currency"
                      value={clientForm.reporting_currency}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, reporting_currency: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-residency-country">
                      Residency Country
                    </label>
                    <input
                      id="edit-residency-country"
                      value={clientForm.residency_country}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, residency_country: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-tax-country">
                      Tax Country
                    </label>
                    <input
                      id="edit-tax-country"
                      value={clientForm.tax_country}
                      onChange={(event) => setClientForm({ ...clientForm, tax_country: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-treaty-country">
                      Treaty Country
                    </label>
                    <input
                      id="edit-treaty-country"
                      value={clientForm.treaty_country}
                      onChange={(event) =>
                        setClientForm({ ...clientForm, treaty_country: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-tax-id">
                      Tax ID
                    </label>
                    <input
                      id="edit-tax-id"
                      value={clientForm.tax_id}
                      onChange={(event) => setClientForm({ ...clientForm, tax_id: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setFormMode(null)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={formSaving}
                    className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200"
                  >
                    {formSaving ? "Saving..." : "Save Changes"}
                  </button>
                </div>
              </form>
            </div>
          ) : null}
          {accountFormOpen && selectedId ? (
            <div className="rounded-2xl border border-slate-800/60 bg-ink-950/40 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Add Account</p>
                  <p className="text-sm text-slate-100 font-medium">New Subaccount</p>
                </div>
                <button
                  type="button"
                  onClick={() => setAccountFormOpen(false)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
              </div>
              <form className="mt-4 space-y-4" onSubmit={handleAddAccount}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="account-name">
                      Account Name
                    </label>
                    <input
                      id="account-name"
                      value={accountForm.account_name}
                      onChange={(event) =>
                        setAccountForm({ ...accountForm, account_name: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Primary Brokerage"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="account-type">
                      Account Type
                    </label>
                    <input
                      id="account-type"
                      value={accountForm.account_type}
                      onChange={(event) =>
                        setAccountForm({ ...accountForm, account_type: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Taxable"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="ownership-type">
                      Ownership Type
                    </label>
                    <input
                      id="ownership-type"
                      value={accountForm.ownership_type}
                      onChange={(event) =>
                        setAccountForm({ ...accountForm, ownership_type: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Individual"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="custodian">
                      Custodian
                    </label>
                    <input
                      id="custodian"
                      value={accountForm.custodian}
                      onChange={(event) =>
                        setAccountForm({ ...accountForm, custodian: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Fidelity"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs text-slate-400" htmlFor="tags">
                      Tags
                    </label>
                    <input
                      id="tags"
                      value={accountForm.tags}
                      onChange={(event) => setAccountForm({ ...accountForm, tags: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      placeholder="Retirement, Core"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setAccountFormOpen(false)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={formSaving}
                    className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200"
                  >
                    {formSaving ? "Saving..." : "Add Account"}
                  </button>
                </div>
              </form>
            </div>
          ) : null}
          {accountEditOpen && selectedId && selectedAccount !== "portfolio" ? (
            <div className="rounded-2xl border border-slate-800/60 bg-ink-950/40 p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Edit Account</p>
                  <p className="text-sm text-slate-100 font-medium">Update Subaccount</p>
                </div>
                <button
                  type="button"
                  onClick={() => setAccountEditOpen(false)}
                  className="text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
              </div>
              <form className="mt-4 space-y-4" onSubmit={handleUpdateAccount}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-account-name">
                      Account Name
                    </label>
                    <input
                      id="edit-account-name"
                      value={accountEditForm.account_name}
                      onChange={(event) =>
                        setAccountEditForm({ ...accountEditForm, account_name: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-account-type">
                      Account Type
                    </label>
                    <input
                      id="edit-account-type"
                      value={accountEditForm.account_type}
                      onChange={(event) =>
                        setAccountEditForm({ ...accountEditForm, account_type: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-ownership-type">
                      Ownership Type
                    </label>
                    <input
                      id="edit-ownership-type"
                      value={accountEditForm.ownership_type}
                      onChange={(event) =>
                        setAccountEditForm({ ...accountEditForm, ownership_type: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400" htmlFor="edit-custodian">
                      Custodian
                    </label>
                    <input
                      id="edit-custodian"
                      value={accountEditForm.custodian}
                      onChange={(event) =>
                        setAccountEditForm({ ...accountEditForm, custodian: event.target.value })
                      }
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs text-slate-400" htmlFor="edit-tags">
                      Tags
                    </label>
                    <input
                      id="edit-tags"
                      value={accountEditForm.tags}
                      onChange={(event) => setAccountEditForm({ ...accountEditForm, tags: event.target.value })}
                      className="mt-2 w-full rounded-xl bg-ink-950/60 border border-slate-800 px-3 py-2 text-sm text-slate-200"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setAccountEditOpen(false)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={formSaving}
                    className="rounded-full border border-emerald-400/70 px-4 py-1 text-xs text-emerald-200"
                  >
                    {formSaving ? "Saving..." : "Save Account"}
                  </button>
                </div>
              </form>
            </div>
          ) : null}
          {!selectedId ? (
            <div className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <KpiCard label="Clients" value={`${summary.clients}`} tone="text-green-300" />
                <KpiCard label="Accounts" value={`${summary.accounts}`} tone="text-slate-100" />
                <KpiCard label="Holdings" value={`${summary.holdings}`} tone="text-slate-100" />
              </div>
              <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-6 text-sm text-slate-100">
                <p className="text-slate-100 font-medium">Select a client to load analytics.</p>
                <p className="mt-2 text-slate-300">
                  Choose a profile from the client list to review its portfolio value, risk, holdings,
                  and advanced analysis.
                </p>
              </div>
            </div>
          ) : (
            <div className="portfolio-context-bar">
              <div className="portfolio-context-group">
                <p className="portfolio-context-label">History window</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {intervals.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setInterval(opt)}
                      className={`rounded-full border px-3 py-1 text-[11px] ${
                        interval === opt
                          ? "border-green-400/70 text-green-200"
                          : "border-slate-700 text-slate-300"
                      }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
              <div className="portfolio-context-group">
                <label htmlFor="account-scope" className="portfolio-context-label">
                  Portfolio scope
                </label>
                <select
                  id="account-scope"
                  name="account-scope"
                  value={selectedAccount}
                  onChange={(event) => setSelectedAccount(event.target.value)}
                  className="mt-2 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                >
                  <option value="portfolio">Client Portfolio</option>
                  {accountOptions.map((account) => (
                    <option key={account.value} value={account.value}>
                      {account.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="portfolio-context-group text-xs text-slate-300">
                <p className="portfolio-context-label">Data status</p>
                {dashboard?.warnings?.length ? (
                  <div className="mt-2 space-y-1 text-amber-300">
                    {dashboard.warnings.map((warn) => (
                      <p key={warn}>{warn}</p>
                    ))}
                  </div>
                ) : null}
                <p className="mt-2" role="status">{dashboardLoading ? "Loading market snapshot…" : dashboard ? `${dashboard.market_snapshot?.label || "Snapshot data; not a live quote stream."}${dashboard.market_snapshot?.cache ? ` Cache: ${dashboard.market_snapshot.cache}.` : ""}` : "Market snapshot unavailable."}</p>
                <button type="button" disabled={dashboardLoading} onClick={() => setDashboardEpoch(value => value + 1)} className="mt-2 rounded-full border border-slate-700 px-3 py-1 disabled:opacity-50">
                  {dashboardLoading ? "Refreshing…" : "Refresh snapshot"}
                </button>
              </div>
              <details className="portfolio-manage">
                <summary>Manage client and accounts</summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setFormMode("edit");
                      setAccountFormOpen(false);
                      setFormError(null);
                    }}
                    className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-100 hover:text-green-500"
                  >
                    Edit Client
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAccountFormOpen(true);
                      setFormMode(null);
                      resetAccountForm();
                      setFormError(null);
                    }}
                    className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-100 hover:text-green-500"
                  >
                    Add Account
                  </button>
                  {selectedAccount !== "portfolio" ? (
                    <button
                      type="button"
                      onClick={() => {
                        setAccountEditOpen(true);
                        setAccountFormOpen(false);
                        setFormMode(null);
                        setFormError(null);
                      }}
                      className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-100 hover:text-green-500"
                    >
                      Edit Account
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setSelectedId(null)}
                    className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-100 hover:text-green-500"
                  >
                    Back to overview
                  </button>
                </div>
              </details>
            </div>
          )}

          {selectedId ? (
            activeTotals ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
                <KpiCard
                  label="Total Value"
                  value={activeTotals.total_value == null ? "Unavailable" : `$${activeTotals.total_value.toFixed(2)}`}
                  tone="text-green-300"
                />
                <KpiCard
                  label="Market Value"
                  value={`$${activeTotals.market_value.toFixed(2)}`}
                  tone="text-slate-100"
                />
                <KpiCard
                  label="Manual Value"
                  value={activeTotals.manual_value == null ? "Unavailable" : `$${activeTotals.manual_value.toFixed(2)}`}
                  tone="text-slate-100"
                />
                <KpiCard
                  label="Holdings Count"
                  value={`${activeTotals.holdings_count}`}
                  tone="text-slate-100"
                />
              </div>
            ) : (
              <div className="rounded-xl border border-slate-700 bg-slate-950/50 p-6 text-sm text-slate-300">
                {dashboardLoading ? "Loading portfolio snapshot..." : "Portfolio snapshot unavailable. Refresh to retry."}
              </div>
            )
          ) : null}

          {selectedId ? (
            <>
              <Collapsible
                title="Client Profile"
                meta={detail?.name || "Loading"}
                open={profileOpen}
                onToggle={() => setProfileOpen((prev) => !prev)}
              >
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs text-slate-100">
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Tax Profile</p>
                <div className="space-y-2">
                  {profileRows.map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between">
                      <span className="text-slate-300">{label}</span>
                      <span className="text-slate-100">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Accounts</p>
                {accountRows.length ? (
                  <div className="space-y-3">
                    {accountRows.map((account) => (
                      <div key={account.id} className="rounded-lg border border-slate-800/60 p-3">
                        <p className="text-slate-100 font-medium">{account.name}</p>
                        <p className="text-[11px] text-slate-400">{account.id}</p>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-100">
                          <span>Type: {account.type}</span>
                          <span>Custodian: {account.custodian}</span>
                          <span>Ownership: {account.ownership}</span>
                          <span>Tax Keys: {account.taxKeys}</span>
                          <span className="col-span-2">Tags: {account.tags}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400">No accounts available.</p>
                )}
              </div>
            </div>
              </Collapsible>

              <Collapsible
                title="Portfolio History"
                meta={dashboard?.interval ? `${dashboard.interval} history` : "Loading"}
                open={historyOpen}
                onToggle={() => setHistoryOpen((prev) => !prev)}
              >
            {dashboard?.history?.length ? (
              <AreaSparkline
                data={dashboard.history}
                height={240}
                title="Portfolio value over time"
                description="Use this trend to see how the selected client or account value changed during the chosen history window."
                yLabel="Portfolio Value"
                valueFormatter={(value) =>
                  value.toLocaleString(undefined, {
                    style: "currency",
                    currency: detail?.reporting_currency || "USD",
                    maximumFractionDigits: 0,
                  })
                }
              />
            ) : (
              <p className="text-xs text-slate-400">
                Historical values are not available yet. Add holdings with price history or choose a longer history window.
              </p>
            )}
              </Collapsible>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Collapsible
                  title="Risk Metrics"
                  meta={dashboard?.risk?.risk_profile || "Loading"}
                  open={riskOpen}
                  onToggle={() => setRiskOpen((prev) => !prev)}
                >
              <VisualizationGuide
                summary="These measures describe return, variability, downside exposure, and benchmark behavior for the selected scope."
                details={[
                  "Percentages are shown in their natural financial units; ratio metrics are unitless.",
                  "Higher risk-adjusted-return ratios are generally preferable, but they should be read with the available sample window and warnings.",
                  "Value at Risk and Conditional Value at Risk summarize historical one-period outcomes; they are not guarantees of maximum loss.",
                  ...riskMetricRows.map(
                    (metric) => `${metric.label} (${metric.technical}): ${metric.description}`
                  ),
                ]}
              />
              {dashboard?.risk?.error ? (
                <p className="text-xs text-amber-300">{dashboard.risk.error}</p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-100">
                  {riskMetricRows.map((metric) => (
                    <div key={metric.key} className="risk-metric-row">
                      <span>
                        <strong>{metric.label}</strong>
                        <small>{metric.technical}</small>
                      </span>
                      <span className="text-slate-100">{metric.displayValue}</span>
                    </div>
                  ))}
                </div>
              )}
                </Collapsible>
                <Collapsible
                  title="Return Distribution"
                  meta={dashboard?.risk?.meta || "Loading"}
                  open={distributionOpen}
                  onToggle={() => setDistributionOpen((prev) => !prev)}
                >
              {dashboard?.risk?.distribution?.length ? (
                <DistributionBars data={dashboard.risk.distribution} height={200} />
              ) : (
              <p className="text-xs text-slate-400">
                A return distribution needs enough historical observations. Choose a longer history window or add price history.
              </p>
            )}
                </Collapsible>
              </div>

              <Collapsible
                title="Market Regime Analysis"
                meta="Advanced"
                open={regimeOpen}
                onToggle={() => setRegimeOpen((prev) => !prev)}
                mountWhenOpen
              >
              <VisualizationGuide
                summary="This analysis groups observed returns into market states and estimates how often the series moved from one state to another."
                details={[
                  "The model is descriptive: it summarizes transitions in the selected history and does not guarantee the next state.",
                  "A high surface point means that transition occurred with higher estimated probability.",
                  "Use this view to understand state persistence and transition behavior, not as a standalone trade signal.",
                ]}
              />
              <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-5">
                <Surface3D
                  title="Market State Transition Probability"
                  z={dashboard?.regime?.transition_matrix || []}
                  x={Object.keys(dashboard?.regime?.state_probs || {})}
                  y={Object.keys(dashboard?.regime?.state_probs || {})}
                  axis={{
                    x_label: "Next Market State",
                    y_label: "Current Market State",
                    z_label: "Transition Probability",
                    z_unit: "0 to 1",
                  }}
                  description="Shows the estimated probability of moving from each current market state to each next state."
                  howToRead={[
                    "Move across X to compare possible next states.",
                    "Move across Y to choose the current state.",
                    "Higher Z values mean the transition occurred more often in the selected history.",
                  ]}
                  emptyMessage="Market-state transitions need more historical observations. Choose a longer window or add price history."
                />
                <div className="space-y-4">
                  <div className="glass-panel rounded-2xl p-5">
                    <p className="text-xs font-semibold text-slate-200">Stationary Distribution</p>
                    <div className="mt-3 space-y-2 text-xs text-slate-100">
                      {dashboard?.regime?.error ? (
                        <p className="text-amber-300">
                          {dashboard.regime.error_detail || dashboard.regime.error}
                        </p>
                      ) : dashboard?.regime?.state_probs ? (
                        Object.entries(dashboard.regime.state_probs).map(([key, value]) => (
                          <div key={key} className="flex items-center justify-between">
                            <span className="text-slate-300">{key}</span>
                            <span className="text-green-300">{(value * 100).toFixed(1)}%</span>
                          </div>
                        ))
                      ) : (
                        <p className="text-slate-400">No regime surface available.</p>
                      )}
                    </div>
                  </div>
                  <div className="glass-panel rounded-2xl p-5">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-slate-200">Regime Window</p>
                      <p className="text-[11px] text-green-300">
                        {dashboard?.regime?.window?.interval || dashboard?.interval || "n/a"}
                      </p>
                    </div>
                    {dashboard?.regime?.window?.series?.length ? (
                      <div className="mt-3">
                        <AreaSparkline
                          data={dashboard.regime.window.series}
                          height={160}
                          color="#48f1a6"
                        />
                        <p className="mt-2 text-[11px] text-slate-400">
                          Samples {dashboard?.regime?.samples ?? 0}
                        </p>
                      </div>
                    ) : dashboard?.regime?.error_detail ? (
                      <p className="mt-3 text-xs text-amber-300">
                        {dashboard.regime.error_detail}
                      </p>
                    ) : (
                      <p className="mt-3 text-xs text-slate-400">
                        No regime window data available.
                      </p>
                    )}
                  </div>
                </div>
              </div>
              </Collapsible>

              <Collapsible
                title="Pattern Analysis"
                meta={!patternOpen ? "Load on demand" : patternsError || patterns?.error ? "Unavailable" : patterns ? "Snapshot analysis" : "Loading…"}
                open={patternOpen}
                mountWhenOpen
                onToggle={() => setPatternOpen((prev) => !prev)}
              >
            {!patterns && !patternsError ? <p className="text-xs text-slate-300" role="status">Loading pattern analysis…</p> : patternsError || patterns?.error ? (
              <p className="text-xs text-amber-300">{patternsError || patterns?.error}</p>
            ) : (
              <div className="space-y-4">
                <VisualizationGuide
                  summary="Pattern analysis describes complexity, persistence, repeating shapes, and frequency structure in the selected return history."
                  details={[
                    "Entropy measures irregularity; it is not a quality score.",
                    "Hurst describes observed persistence or mean-reversion tendencies; it is not a forecast.",
                    "Frequency power shows recurring cycles in the sampled history and should be read with the selected interval.",
                  ]}
                />
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 text-xs text-slate-100">
                  <KpiCard label="Return Irregularity (Entropy)" value={patterns?.entropy != null ? patterns.entropy.toFixed(3) : "—"} tone="text-green-300" />
                  <KpiCard label="Sequence Irregularity (Permutation Entropy)" value={patterns?.perm_entropy != null ? patterns.perm_entropy.toFixed(3) : "—"} tone="text-slate-100" />
                  <KpiCard label="Persistence Tendency (Hurst)" value={patterns?.hurst != null ? patterns.hurst.toFixed(3) : "—"} tone="text-slate-100" />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <Surface3D
                    title="Return History Surface"
                    z={patterns?.wave_surface?.z || []}
                    x={patterns?.wave_surface?.x}
                    y={patterns?.wave_surface?.y}
                    axis={patterns?.wave_surface?.axis}
                    height={300}
                    description="Arranges the return history into consecutive rows so repeating shapes and abrupt changes are easier to inspect."
                    howToRead={[
                      "X is the observation position within each row.",
                      "Y moves through consecutive windows of the selected history.",
                      "Z is the observed return value; high and low points show larger positive and negative moves.",
                    ]}
                  />
                  <Surface3D
                    title="Recurring Cycle Strength"
                    z={patterns?.fft_surface?.z || []}
                    x={patterns?.fft_surface?.x}
                    y={patterns?.fft_surface?.y}
                    axis={patterns?.fft_surface?.axis}
                    height={300}
                    description="Shows how the strength of recurring return cycles changes through the selected history."
                    howToRead={[
                      "X is cycle frequency: farther right represents faster repetition.",
                      "Y moves through consecutive windows of the selected history.",
                      "Z is log power: higher points indicate a stronger recurring component at that frequency.",
                    ]}
                  />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs text-slate-100">
                  <div className="rounded-xl border border-slate-700 p-4">
                    <p className="text-xs font-semibold text-slate-200 mb-2">Motif Matches</p>
                    {patterns?.motifs?.length ? (
                      patterns.motifs.map((motif) => (
                        <div key={motif.window} className="flex items-center justify-between">
                          <span className="text-slate-300">{motif.window}</span>
                          <span className="text-green-300">{motif.distance.toFixed(3)}</span>
                        </div>
                      ))
                    ) : (
                      <p className="text-slate-400">No motif matches.</p>
                    )}
                  </div>
                  <div className="rounded-xl border border-slate-700 p-4">
                    <p className="text-xs font-semibold text-slate-200 mb-2">Change Points</p>
                    {patterns?.change_points?.length ? (
                      <p className="text-slate-100">{patterns.change_points.length} detected shifts</p>
                    ) : (
                      <p className="text-slate-400">No change points detected.</p>
                    )}
                  </div>
                </div>
              </div>
            )}
              </Collapsible>

              <Collapsible
                title="Holdings Snapshot"
                meta={`${activeHoldings.length} positions`}
                open={holdingsOpen}
                onToggle={() => setHoldingsOpen((prev) => !prev)}
              >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {activeHoldings.map((holding) => (
                <div key={holding.ticker} className="rounded-xl border border-slate-700 p-4">
                  <p className="text-slate-100 font-medium">{holding.ticker}</p>
                  <p className="text-xs text-slate-300">{holding.name || "—"} • {holding.sector || "N/A"}</p>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-100">
                    <span>Qty {holding.quantity.toFixed(2)}</span>
                    <span>${holding.market_value.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
              </Collapsible>

              {selectedAccount !== "portfolio" ? (
              <Collapsible
                title="Holdings book"
                meta="Lots, cash, and cash-flow events"
                open={lotsOpen}
                onToggle={() => setLotsOpen((prev) => !prev)}
              >
            {selectedId && selectedAccountDetail ? (
              <PositionsBook
                clientId={selectedId}
                accountId={selectedAccount}
                disabled={formSaving}
                onSaved={async () => {
                  invalidateApiCache("/api/clients/");
                  setDashboardEpoch((value) => value + 1);
                  const detailPayload = await apiGet<ClientDetail>(`/api/clients/${encodeURIComponent(selectedId)}`);
                  setDetail(detailPayload);
                  await refreshIndex();
                }}
              />
            ) : (
              <p className="text-xs text-slate-400">Select an account to manage lots and cash.</p>
            )}
              </Collapsible>
              ) : null}

              <Collapsible
                title="Diagnostics"
                meta="Concentration + Movers"
                open={diagnosticsOpen}
                onToggle={() => setDiagnosticsOpen((prev) => !prev)}
              >
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs text-slate-100">
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Sector Concentration</p>
                {dashboard?.diagnostics?.sectors?.length ? (
                  <div className="space-y-2">
                    {dashboard.diagnostics.sectors.map((row) => (
                      <div key={row.sector} className="flex items-center justify-between">
                        <span className="text-slate-300">{row.sector}</span>
                        <span className="text-green-300">{(row.pct * 100).toFixed(1)}%</span>
                      </div>
                    ))}
                    <div className="pt-2 text-slate-300">HHI {dashboard.diagnostics.hhi == null ? "unavailable without priced holdings" : dashboard.diagnostics.hhi.toFixed(3)}</div>
                  </div>
                ) : (
                  <p className="text-slate-400">No sector data available.</p>
                )}
              </div>
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Top Movers (1D)</p>
                {dashboard?.diagnostics ? (
                  <div className="space-y-2">
                    {(dashboard.diagnostics.gainers || []).map((row) => (
                      <div key={`gain-${row.ticker}`} className="flex items-center justify-between">
                        <span className="text-slate-100">{row.ticker}</span>
                        <span className="text-green-300">{(row.pct * 100).toFixed(2)}%</span>
                      </div>
                    ))}
                    {(dashboard.diagnostics.losers || []).map((row) => (
                      <div key={`loss-${row.ticker}`} className="flex items-center justify-between">
                        <span className="text-slate-100">{row.ticker}</span>
                        <span className="text-amber-300">{(row.pct * 100).toFixed(2)}%</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400">No mover data available.</p>
                )}
              </div>
            </div>
              </Collapsible>

              <Collapsible
                title="Manual Assets"
                meta={`${dashboard?.manual_holdings?.length || 0} entries`}
                open={manualOpen}
                onToggle={() => setManualOpen((prev) => !prev)}
              >
            {dashboard?.manual_holdings?.length ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {dashboard.manual_holdings.map((holding, idx) => (
                  <div key={`${holding.name || "manual"}-${idx}`} className="rounded-xl border border-slate-700 p-4 text-xs text-slate-100">
                    <p className="text-slate-100">{holding.name || "Manual Asset"}</p>
                    <p className="text-slate-300">${(holding.total_value || 0).toFixed(2)}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No manual assets recorded.</p>
            )}
              </Collapsible>
            </>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
