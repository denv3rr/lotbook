import { Card } from "../components/ui/Card";
import { MeterBar } from "../components/ui/Charts";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { KpiCard } from "../components/ui/KpiCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { Modal } from "../components/ui/Modal";
import {
  apiPost,
  clearApiKey,
  getApiKeyScope,
  getAuthHint,
  setApiKey as setApiKeyLocal,
  useApi
} from "../lib/api";
import { useSystemMetrics } from "../lib/systemMetrics";
import { useState } from "react";

type DiagnosticsPayload = {
  system?: {
    hostname?: string;
    ip?: string;
    os?: string;
    cpu_usage?: string;
    cpu_cores?: number | string;
    mem_usage?: string;
    python_version?: string;
    finnhub_status?: boolean;
    psutil_available?: boolean;
    user?: string;
  };
  metrics?: {
    disk_total_gb?: number | null;
    disk_used_gb?: number | null;
    disk_free_gb?: number | null;
    disk_percent?: number | null;
  };
  feeds?: {
    flights?: {
      configured?: boolean;
      url_sources?: number;
      path_sources?: number;
    };
    shipping?: { configured?: boolean };
    opensky?: { credentials_set?: boolean };
    registry?: {
      sources?: Array<{
        id?: string;
        label?: string;
        category?: string;
        configured?: boolean;
        status?: string;
      }>;
    };
    summary?: {
      total?: number;
      configured?: number;
      warnings?: string[];
      health_counts?: {
        ok?: number;
        degraded?: number;
        backoff?: number;
        unknown?: number;
      };
    };
  };
  trackers?: { warning_count?: number; count?: number };
  intel?: {
    news_cache?: {
      status?: string;
      items?: number;
      raw_items?: number;
      duplicate_items?: number;
      age_hours?: number | null;
    };
  };
  clients?: { clients?: number; accounts?: number; holdings?: number; lots?: number };
  duplicates?: {
    accounts?: { count?: number; clients?: number };
    client_names?: { count?: number; groups?: number };
    news?: { count?: number };
  };
  orphans?: { holdings?: number; lots?: number };
  reports?: { items?: number; status?: string };
};

type HealthPayload = {
  status?: string;
};

type DuplicateCleanupResponse = {
  removed?: number;
  clients?: number;
  remaining?: { count?: number; clients?: number };
};

type MaintenanceResponse = {
  normalized?: boolean;
  message?: string;
  cleared?: boolean;
  removed_holdings?: number;
  removed_lots?: number;
};

export default function System() {
  const [cleanupMessage, setCleanupMessage] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    onConfirm: () => Promise<void>;
  } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [apiKeyOpen, setApiKeyOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiKeyPersist, setApiKeyPersist] = useState(false);
  const [apiKeyBusy, setApiKeyBusy] = useState(false);
  const [apiKeyError, setApiKeyError] = useState<string | null>(null);
  const [apiKeyNotice, setApiKeyNotice] = useState<string | null>(null);
  const { data, error, refresh } = useApi<DiagnosticsPayload>("/api/tools/diagnostics", {
    interval: 60000
  });
  const { data: health } = useApi<HealthPayload>("/api/health", { interval: 60000 });
  const { metrics } = useSystemMetrics();
  const cpuPercent = metrics?.cpu_percent ?? null;
  const memPercent = metrics?.mem_percent ?? null;
  const diskPercent = metrics?.disk_percent ?? null;
  const swapPercent = metrics?.swap_percent ?? null;
  const authHint = getAuthHint();
  const errorMessages = [
    error
      ? `Diagnostics failed: ${error}${error.includes("401") || error.includes("403") ? ` (${authHint})` : ""}`
      : null
  ].filter(Boolean) as string[];
  const apiKeyScope = getApiKeyScope();

  const duplicateCount = data?.duplicates?.accounts?.count ?? 0;
  const duplicateClients = data?.duplicates?.accounts?.clients ?? 0;
  const duplicateClientNames = data?.duplicates?.client_names?.count ?? 0;
  const duplicateClientGroups = data?.duplicates?.client_names?.groups ?? 0;
  const duplicateNewsItems = data?.duplicates?.news?.count ?? 0;
  const orphanHoldings = data?.orphans?.holdings ?? 0;
  const orphanLots = data?.orphans?.lots ?? 0;
  const feedTotal = data?.feeds?.summary?.total ?? 0;
  const feedConfigured = data?.feeds?.summary?.configured ?? 0;
  const feedWarnings = data?.feeds?.summary?.warnings ?? [];
  const feedHealth = data?.feeds?.summary?.health_counts;
  const feedOk = feedHealth?.ok ?? 0;
  const feedDegraded = feedHealth?.degraded ?? 0;
  const feedBackoff = feedHealth?.backoff ?? 0;
  const feedSources = data?.feeds?.registry?.sources ?? [];
  const flaggedFeeds = feedSources.filter((source) =>
    source?.status === "degraded" || source?.status === "backoff"
  );

  const openConfirm = (title: string, message: string, onConfirm: () => Promise<void>) => {
    setConfirmAction({ title, message, onConfirm });
  };

  const handleConfirm = async () => {
    if (!confirmAction) return;
    setConfirmBusy(true);
    try {
      await confirmAction.onConfirm();
    } finally {
      setConfirmBusy(false);
      setConfirmAction(null);
    }
  };

  const onNormalize = () => {
    openConfirm(
      "Normalize legacy lots",
      "Normalize legacy lot timestamps? This will update stored client data.",
      async () => {
        try {
          const result = await apiPost<MaintenanceResponse>(
            "/api/maintenance/normalize-lots",
            { confirm: true }
          );
          setCleanupMessage(result.message || "Normalization complete.");
        } catch (err) {
          const message = err instanceof Error ? err.message : "Normalization failed.";
          setCleanupMessage(message);
        }
      }
    );
  };

  const onClearCache = () => {
    openConfirm(
      "Clear report cache",
      "Clear the report cache? This will remove cached report artifacts.",
      async () => {
        try {
          const result = await apiPost<MaintenanceResponse>(
            "/api/maintenance/clear-report-cache",
            { confirm: true }
          );
          if (result.cleared) {
            setCleanupMessage("Report cache cleared.");
          } else {
            setCleanupMessage("Report cache already empty.");
          }
          refresh();
        } catch (err) {
          const message = err instanceof Error ? err.message : "Report cache cleanup failed.";
          setCleanupMessage(message);
        }
      }
    );
  };

  const onCleanupOrphans = () => {
    const totalOrphans = orphanHoldings + orphanLots;
    if (!totalOrphans) {
      setCleanupMessage("No orphaned holdings or lots detected.");
      return;
    }
    openConfirm(
      "Cleanup orphaned records",
      `Remove ${orphanHoldings} orphaned holding${orphanHoldings === 1 ? "" : "s"} and ${orphanLots} orphaned lot${orphanLots === 1 ? "" : "s"}?`,
      async () => {
        try {
          const result = await apiPost<MaintenanceResponse>(
            "/api/maintenance/cleanup-orphans",
            { confirm: true }
          );
          setCleanupMessage(
            `Removed ${result.removed_holdings ?? 0} orphaned holdings and ${result.removed_lots ?? 0} orphaned lots.`
          );
          refresh();
        } catch (err) {
          const message = err instanceof Error ? err.message : "Orphan cleanup failed.";
          setCleanupMessage(message);
        }
      }
    );
  };

  const onCleanupDuplicates = () => {
    if (!duplicateCount) return;
    openConfirm(
      "Cleanup duplicate accounts",
      `Remove ${duplicateCount} duplicate account${duplicateCount === 1 ? "" : "s"} across ${duplicateClients} client${duplicateClients === 1 ? "" : "s"}? Originals will be preserved.`,
      async () => {
        try {
          const result = await apiPost<DuplicateCleanupResponse>(
            "/api/clients/duplicates/cleanup",
            { confirm: true }
          );
          const remaining = result.remaining?.count ?? 0;
          const removed = result.removed ?? 0;
          if (remaining > 0) {
            setCleanupMessage(
              `Removed ${removed} duplicate account${removed === 1 ? "" : "s"}. ${remaining} still remain.`
            );
          } else {
            setCleanupMessage(
              `Removed ${removed} duplicate account${removed === 1 ? "" : "s"}.`
            );
          }
          refresh();
        } catch (err) {
          const message = err instanceof Error ? err.message : "Duplicate cleanup failed.";
          setCleanupMessage(message);
        }
      }
    );
  };

  const onSetApiKey = () => {
    setApiKeyInput("");
    setApiKeyPersist(false);
    setApiKeyError(null);
    setApiKeyOpen(true);
  };

  const onClearApiKey = () => {
    clearApiKey();
    setApiKeyError(null);
    setApiKeyNotice("Browser API key cleared.");
  };

  const onSaveApiKey = async () => {
    const trimmed = apiKeyInput.trim();
    if (!trimmed) {
      setApiKeyError("Enter an API key before saving.");
      return;
    }
    setApiKeyBusy(true);
    setApiKeyError(null);
    try {
      const scope = await setApiKeyLocal(trimmed, { persist: apiKeyPersist });
      setApiKeyNotice(
        scope === "memory"
          ? "Encrypted browser storage is unavailable. The key is active for this page only and will be lost on reload."
          : `API key saved for ${scope === "local" ? "this device" : "this browser session"}.`
      );
      setApiKeyOpen(false);
      setApiKeyInput("");
    } catch (err) {
      setApiKeyError(err instanceof Error ? err.message : "The API key could not be saved.");
    } finally {
      setApiKeyBusy(false);
    }
  };

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader
        label="SYSTEM"
        title="System Settings & Diagnostics"
        right={
          <div className="flex items-center space-x-2">
            <button
              onClick={onSetApiKey}
              className="rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-1 text-xs text-slate-100 hover:border-green-400/40"
            >
              Set API Key
            </button>
            <button
              onClick={onClearApiKey}
              className="rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-1 text-xs text-slate-100 hover:border-green-400/40"
            >
              Clear API Key
            </button>
            <div className="hidden text-[11px] text-slate-400 md:flex">
              Key: {apiKeyScope === "none" ? "unset" : apiKeyScope}
            </div>
          </div>
        }
      />
      <div className="mt-4">
        <ErrorBanner messages={errorMessages} onRetry={refresh} />
      </div>
      {duplicateCount > 0 || duplicateClientNames > 0 || duplicateNewsItems > 0 ? (
        <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              {duplicateCount > 0 ? (
                <p>
                  Duplicate accounts detected: {duplicateCount} across{" "}
                  {duplicateClients} client{duplicateClients === 1 ? "" : "s"}.
                </p>
              ) : null}
              {duplicateClientNames > 0 ? (
                <p>
                  Duplicate client names detected: {duplicateClientNames} duplicate record
                  {duplicateClientNames === 1 ? "" : "s"} across {duplicateClientGroups} name group
                  {duplicateClientGroups === 1 ? "" : "s"}.
                </p>
              ) : null}
              {duplicateNewsItems > 0 ? (
                <p>
                  Duplicate raw news entries detected: {duplicateNewsItems}. Counts now dedupe at load time, but the cache should still be reviewed.
                </p>
              ) : null}
            </div>
            {duplicateCount > 0 ? (
              <button
                onClick={onCleanupDuplicates}
                className="rounded-lg border border-amber-400/50 px-3 py-1 text-xs text-amber-100 hover:border-amber-300"
              >
                Remove account duplicates
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      {cleanupMessage ? (
        <div className="mt-3 rounded-xl border border-slate-700/60 bg-slate-900/70 p-3 text-xs text-slate-200">
          {cleanupMessage}
        </div>
      ) : null}
      {apiKeyNotice ? (
        <div
          className="mt-3 rounded-xl border border-sky-400/30 bg-sky-400/10 p-3 text-xs text-sky-100"
          role="status"
        >
          {apiKeyNotice}
        </div>
      ) : null}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-4 gap-4">
        <KpiCard label="Clients" value={`${data?.clients?.clients ?? 0}`} tone="text-green-300" />
        <KpiCard label="Accounts" value={`${data?.clients?.accounts ?? 0}`} tone="text-slate-100" />
        <KpiCard label="Holdings" value={`${data?.clients?.holdings ?? 0}`} tone="text-slate-100" />
        <KpiCard label="Tracker Signals" value={`${data?.trackers?.count ?? 0}`} tone="text-green-300" />
      </div>
      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 text-sm">
        <div className="rounded-xl border border-slate-700 p-4">
          <p className="text-slate-100 font-medium">Data Management</p>
          <div className="mt-3 space-y-2">
            <button
              onClick={onNormalize}
              className="w-full rounded-lg border border-slate-700 px-3 py-2 text-left text-slate-100 hover:border-green-400/40"
            >
              Normalize Lot Timestamps
            </button>
            <button
              onClick={onClearCache}
              className="w-full rounded-lg border border-slate-700 px-3 py-2 text-left text-slate-100 hover:border-green-400/40"
            >
              Clear Report Cache
            </button>
            <button
              onClick={onCleanupOrphans}
              className="w-full rounded-lg border border-slate-700 px-3 py-2 text-left text-slate-100 hover:border-green-400/40"
            >
              Remove Orphaned Holdings/Lots
            </button>
          </div>
        </div>
        <div className="rounded-xl border border-slate-700 p-4">
          <p className="text-slate-100 font-medium">API Key</p>
          <div className="mt-3 space-y-2">
            <p className="text-xs text-slate-300">
              Current key: {getApiKeyScope() !== "none" ? "********" : "Not set"}
            </p>
          </div>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 text-sm text-slate-100">
        <div className="space-y-2">
          <p className="text-slate-100 font-medium">System</p>
          <p>User: {data?.system?.user || "—"}</p>
          <p>Host: {data?.system?.hostname || "—"}</p>
          <p>IP: {data?.system?.ip || "—"}</p>
          <p>OS: {data?.system?.os || "—"}</p>
          <p>CPU: {data?.system?.cpu_usage || "—"}</p>
          <p>Cores: {data?.system?.cpu_cores ?? "—"}</p>
          <p>Memory: {data?.system?.mem_usage || "—"}</p>
          <p>Python: {data?.system?.python_version || "—"}</p>
          <p>Finnhub Key: {data?.system?.finnhub_status ? "Configured" : "Missing"}</p>
          <p>psutil: {data?.system?.psutil_available ? "Available" : "Missing"}</p>
          <p>API Health: {health?.status || "Unknown"}</p>
          <p>
            Flight Feed:{" "}
            {data?.feeds?.flights?.configured
              ? data?.feeds?.flights?.url_sources || data?.feeds?.flights?.path_sources
                ? "Configured"
                : data?.feeds?.opensky?.credentials_set
                ? "OpenSky (auth)"
                : "OpenSky (anon)"
              : "Missing"}{" "}
            ({data?.feeds?.flights?.url_sources ?? 0} URL / {data?.feeds?.flights?.path_sources ?? 0} file)
          </p>
          <p>Shipping Feed: {data?.feeds?.shipping?.configured ? "Configured" : "Missing"}</p>
          <p>OpenSky Creds: {data?.feeds?.opensky?.credentials_set ? "Present" : "Missing"}</p>
          <p>
            Feed Sources: {feedConfigured}/{feedTotal} configured
            {feedWarnings.length ? ` • ${feedWarnings.length} warning` : ""}
            {feedWarnings.length === 1 ? "" : feedWarnings.length ? "s" : ""}
          </p>
          <p>
            Feed Health: {feedOk} ok • {feedDegraded} degraded • {feedBackoff} backoff
          </p>
          {flaggedFeeds.length ? (
            <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-2 text-xs text-amber-200">
              <p className="font-semibold">Feed issues</p>
              <ul className="mt-1 space-y-1">
                {flaggedFeeds.slice(0, 4).map((source) => (
                  <li key={source.id || source.label}>
                    {source.label || source.id} • {source.status}
                  </li>
                ))}
                {flaggedFeeds.length > 4 ? (
                  <li>+{flaggedFeeds.length - 4} more</li>
                ) : null}
              </ul>
            </div>
          ) : null}
          <p>Tracker Warnings: {data?.trackers?.warning_count ?? "—"}</p>       
          <p>
            Orphaned Holdings: {orphanHoldings} • Orphaned Lots: {orphanLots}
          </p>
          <p>
            News Cache: {data?.intel?.news_cache?.status || "—"} ({data?.intel?.news_cache?.items ?? 0})
            {data?.intel?.news_cache?.age_hours !== undefined && data?.intel?.news_cache?.age_hours !== null
              ? ` • ${data?.intel?.news_cache?.age_hours}h`
              : ""}
          </p>
          <p>
            News Duplicates: {duplicateNewsItems}
            {data?.intel?.news_cache?.raw_items !== undefined
              ? ` • raw ${data?.intel?.news_cache?.raw_items ?? 0} / unique ${data?.intel?.news_cache?.items ?? 0}`
              : ""}
          </p>
          <p>
            Client Name Duplicates: {duplicateClientNames}
            {duplicateClientGroups ? ` • ${duplicateClientGroups} groups` : ""}
          </p>
          <p>Lots: {data?.clients?.lots ?? "—"}</p>
          <p>Report Cache: {data?.reports?.status || "—"} ({data?.reports?.items ?? 0})</p>
        </div>
        <div className="space-y-2">
          <p className="text-slate-100 font-medium">Utilization</p>
          <p className="text-xs font-semibold text-slate-200">CPU Load</p>
          <MeterBar value={cpuPercent ?? 0} height={70} max={100} />
          <p className="text-xs font-semibold text-slate-200 mt-3">Memory Load</p>
          <MeterBar value={memPercent ?? 0} height={70} max={100} />
          <p className="text-xs font-semibold text-slate-200 mt-3">Disk Usage</p>
          <MeterBar value={diskPercent ?? 0} height={70} max={100} />
          <p className="text-xs font-semibold text-slate-200 mt-3">Swap Load</p>
          <MeterBar value={swapPercent ?? 0} height={70} max={100} color="var(--green-300)" />
          <div className="mt-3 text-xs text-slate-300 space-y-1">
            <p>Total: {metrics?.disk_total_gb?.toFixed(2) ?? "—"} GB</p>
            <p>Used: {metrics?.disk_used_gb?.toFixed(2) ?? "—"} GB</p>
            <p>Free: {metrics?.disk_free_gb?.toFixed(2) ?? "—"} GB</p>
          </div>
        </div>
      </div>
      <Modal
        open={Boolean(confirmAction)}
        title={confirmAction?.title ?? ""}
        description={confirmAction?.message}
        onClose={() => (confirmBusy ? null : setConfirmAction(null))}
        footer={
          <>
            <button
              type="button"
              onClick={() => setConfirmAction(null)}
              disabled={confirmBusy}
              className="rounded-full border border-slate-700/70 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={confirmBusy}
              className="rounded-full border border-amber-400/60 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-200 hover:border-amber-300 disabled:opacity-50"
            >
              {confirmBusy ? "Working..." : "Confirm"}
            </button>
          </>
        }
      >
        <p className="text-xs text-slate-300">
          This action cannot be undone. Confirm only if you have recent backups.
        </p>
      </Modal>
      <Modal
        open={apiKeyOpen}
        title="Set API Key"
        description="Encrypted browser storage is used when available. Use session mode for temporary access."
        onClose={() => (apiKeyBusy ? null : setApiKeyOpen(false))}
        footer={
          <>
            <button
              type="button"
              onClick={() => setApiKeyOpen(false)}
              disabled={apiKeyBusy}
              className="rounded-full border border-slate-700/70 px-3 py-1 text-[11px] text-slate-300 hover:border-slate-500"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onSaveApiKey}
              disabled={apiKeyBusy}
              className="rounded-full border border-green-400/60 bg-green-500/10 px-3 py-1 text-[11px] text-green-200 hover:border-green-300"
            >
              {apiKeyBusy ? "Saving..." : "Save Key"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="block text-xs text-slate-300">
            API Key
            <input
              type="password"
              value={apiKeyInput}
              onChange={(event) => setApiKeyInput(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 focus:border-green-400/60 focus:outline-none"
              placeholder="Enter CLEAR_WEB_API_KEY"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={apiKeyPersist}
              onChange={(event) => setApiKeyPersist(event.target.checked)}
            />
            Remember on this device (persists in local storage)
          </label>
          <p className="text-[11px] text-slate-400">
            Rotating keys? Save the new key here and clear old keys on other devices.
          </p>
          {apiKeyError ? (
            <p className="text-[11px] text-rose-300" role="alert">
              {apiKeyError}
            </p>
          ) : null}
        </div>
      </Modal>
    </Card>
  );
}
