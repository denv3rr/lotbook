import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card } from "../components/ui/Card";
import { Collapsible } from "../components/ui/Collapsible";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { SectionHeader } from "../components/ui/SectionHeader";
import { apiGet, useApi } from "../lib/api";

type ClientSummary = {
  client_id: string;
  name: string;
  accounts_count: number;
  holdings_count: number;
};

type ClientIndex = {
  clients: ClientSummary[];
};

type AccountDetail = {
  account_id: string;
  account_name: string;
  account_type?: string;
};

type ClientDetail = ClientSummary & {
  accounts: AccountDetail[];
};

type ReportPayload = {
  content: string;
  format: string;
};

const intervals = ["1W", "1M", "3M", "6M", "1Y"];

export default function Reports() {
  const { data, error: indexError, refresh } = useApi<ClientIndex>("/api/clients", {
    interval: 60000
  });
  const clients = data?.clients ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<string>("portfolio");  
  const [format, setFormat] = useState<"md" | "json">("md");
  const [interval, setInterval] = useState("1M");
  const [detail, setDetail] = useState<boolean>(false);
  const [report, setReport] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const { data: clientDetail, error: detailError } = useApi<ClientDetail>(
    selectedId ? `/api/clients/${encodeURIComponent(selectedId)}` : "",
    { enabled: !!selectedId }
  );

  const clientLabel = useMemo(
    () => (selectedId ? `Client ${selectedId}` : "Select a client"),
    [selectedId]
  );

  const runReport = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      const path =
        selectedAccount === "portfolio"
          ? `/api/reports/client/${selectedId}?detail=${detail}&fmt=${format}&interval=${interval}`
          : `/api/reports/client/${selectedId}/accounts/${selectedAccount}?fmt=${format}&interval=${interval}`;
      const payload = await apiGet<ReportPayload>(path, 0);
      setReport(payload.content || "");
      setReportError(null);
    } catch (err) {
      setReport("");
      setReportError(err instanceof Error ? err.message : "Report generation failed.");
    } finally {
      setLoading(false);
    }
  };
  const authHint = "Check LOTBOOK_WEB_API_KEY + localStorage lotbook_api_key.";
  const errorMessages = [
    indexError
      ? `Client index failed: ${indexError}${
          indexError.includes("401") || indexError.includes("403") ? ` (${authHint})` : ""
        }`
      : null,
    detailError ? `Client detail failed: ${detailError}` : null,
    reportError ? `Report failed: ${reportError}` : null
  ].filter(Boolean) as string[];

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader label="REPORTS" title="Client Reporting" right={clientLabel} />
      <div className="mt-4">
        <ErrorBanner messages={errorMessages} onRetry={refresh} />
      </div>
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-3 text-sm text-slate-300">
          {clients.length ? (
            clients.map((client) => (
              <button
                key={client.client_id}
                onClick={() => {
                  setSelectedId(client.client_id);
                  setSelectedAccount("portfolio");
                  setReport("");
                }}
                className={`w-full rounded-xl border px-4 py-3 text-left ${
                  selectedId === client.client_id
                    ? "border-green-400/60 text-green-100"
                    : "border-slate-700 text-slate-100"
                }`}
              >
                <p className="font-medium">{client.name}</p>
                <p className="text-xs text-slate-300">{client.accounts_count} accounts</p>
              </button>
            ))
          ) : (
            <p className="text-xs text-slate-400">
              Add a client in Clients before generating a report.
            </p>
          )}
        </div>
        <div className="lg:col-span-2 space-y-4">
          <Collapsible
            title="Report Filters"
            meta={format.toUpperCase()}
            open={filtersOpen}
            onToggle={() => setFiltersOpen((prev) => !prev)}
          >
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
              <div>
                <label htmlFor="report-format" className="text-xs text-slate-300">
                  Format
                </label>
                <select
                  id="report-format"
                  name="report-format"
                  value={format}
                  onChange={(event) => setFormat(event.target.value as "md" | "json")}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                >
                  <option value="md">Markdown</option>
                  <option value="json">JSON</option>
                </select>
              </div>
              <div>
                <label htmlFor="report-scope" className="text-xs text-slate-300">
                  Scope
                </label>
                <select
                  id="report-scope"
                  name="report-scope"
                  value={selectedAccount}
                  onChange={(event) => setSelectedAccount(event.target.value)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                >
                  <option value="portfolio">Client Portfolio</option>
                  {(clientDetail?.accounts || []).map((account) => (
                    <option key={account.account_id} value={account.account_id}>
                      {account.account_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end gap-3">
                <label htmlFor="report-detail" className="text-xs text-slate-300">
                  Detailed
                </label>
                <button
                  id="report-detail"
                  type="button"
                  onClick={() => setDetail((prev) => !prev)}
                  className={`rounded-xl border px-3 py-2 text-xs ${
                    detail ? "border-green-400/70 text-green-200" : "border-slate-700 text-slate-300"
                  }`}
                >
                  {detail ? "On" : "Off"}
                </button>
              </div>
              <div className="rounded-xl border border-slate-700 p-3">
                <p className="text-xs font-semibold text-slate-200">Interval</p>
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
            </div>
          </Collapsible>
          <div className="flex gap-3">
            <button
              onClick={runReport}
              disabled={!selectedId || loading}
              className="px-4 py-2 rounded-lg border border-green-400/40 text-green-200 hover:bg-green-400/10 disabled:opacity-40"
            >
              Generate Report
            </button>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-950/50 p-4 min-h-[220px]">
            {loading ? (
              <p className="text-xs text-slate-100">Generating report...</p>
            ) : report ? (
              format === "json" ? (
                <pre className="text-xs text-slate-100 whitespace-pre-wrap">{report}</pre>
              ) : (
                <div className="markdown text-sm text-slate-100">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
                </div>
              )
            ) : (
              <p className="text-xs text-slate-100">Select a client to generate reports.</p>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
