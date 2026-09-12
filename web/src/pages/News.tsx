import { useMemo, useState } from "react";
import { Card } from "../components/ui/Card";
import { Collapsible } from "../components/ui/Collapsible";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { SectionHeader } from "../components/ui/SectionHeader";
import { useApi } from "../lib/api";

type IntelMeta = {
  regions: { name: string; industries: string[] }[];
  industries: string[];
  categories: string[];
  sources: string[];
};

type NewsItem = {
  title: string;
  source?: string;
  sources?: string[];
  url?: string;
  published_ts?: number;
  regions?: string[];
  industries?: string[];
  tags?: string[];
};

type NewsPayload = {
  items: NewsItem[];
  cached?: boolean;
  stale?: boolean;
  skipped?: string[];
  health?: Record<string, { last_ok?: number; last_fail?: number; fail_count?: number; backoff_until?: number }>;
};

export default function News() {
  const { data: meta, error: metaError } = useApi<IntelMeta>("/api/intel/meta", {
    interval: 600000
  });
  const [region, setRegion] = useState("Global");
  const [industry, setIndustry] = useState("all");
  const [tickers, setTickers] = useState("");
  const [limit, setLimit] = useState(25);
  const [sources, setSources] = useState<string[]>([]);
  const [forceToken, setForceToken] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    params.set("region", region);
    params.set("industry", industry);
    if (tickers.trim()) {
      params.set("tickers", tickers.trim());
    }
    if (sources.length) {
      params.set("sources", sources.join(","));
    }
    if (forceToken > 0) {
      params.set("force", "true");
      params.set("nonce", String(forceToken));
    }
    return `/api/intel/news?${params.toString()}`;
  }, [limit, region, industry, tickers, sources, forceToken]);

  const { data, error: newsError, refresh } = useApi<NewsPayload>(query, {
    interval: 660000
  });
  const items = data?.items ?? [];
  const regionOptions = meta?.regions?.map((entry) => entry.name) || ["Global"];
  const industryOptions = meta?.industries || ["all"];
  const sourceOptions = meta?.sources || [];
  const authHint = "Check LOTBOOK_WEB_API_KEY + localStorage lotbook_api_key.";

  const formatTimestamp = (ts?: number) => {
    if (!ts) return null;
    const date = new Date(ts * 1000);
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(date);
  };

  const formatAge = (ts?: number) => {
    if (!ts) return null;
    const delta = Math.max(0, Math.floor(Date.now() / 1000) - ts);
    if (delta < 3600) return `${Math.max(1, Math.floor(delta / 60))}m ago`;
    if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
    return `${Math.floor(delta / 86400)}d ago`;
  };
  const formatSources = (item: NewsItem) => {
    const merged = (item.sources || []).filter((value) => typeof value === "string" && Boolean(value.trim()));
    if (!merged.length) {
      return item.source || "Unknown source";
    }
    if (merged.length <= 2) {
      return merged.join(" • ");
    }
    return `${merged.slice(0, 2).join(" • ")} +${merged.length - 2} more`;
  };
  const errorMessages = [
    metaError ? `Signal metadata failed: ${metaError}` : null,
    newsError
      ? `News feed failed: ${newsError}${
          newsError.includes("401") || newsError.includes("403") ? ` (${authHint})` : ""
        }`
      : null
  ].filter(Boolean) as string[];

  const toggleSource = (value: string) => {
    setSources((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  };

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader label="NEWS" title="Market Signals" right={data?.stale ? "Stale" : "Live"} />
      <div className="mt-4">
        <ErrorBanner messages={errorMessages} onRetry={refresh} />
      </div>
      <div className="mt-6 space-y-4 text-sm text-slate-300">
        <Collapsible
          title="Filters"
          meta={`${region} • ${industry}`}
          open={filtersOpen}
          onToggle={() => setFiltersOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <label htmlFor="news-region" className="text-xs text-slate-300">
                Region
              </label>
              <select
                id="news-region"
                name="news-region"
                value={region}
                onChange={(event) => setRegion(event.target.value)}
                className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
              >
                {regionOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="news-industry" className="text-xs text-slate-300">
                Industry
              </label>
              <select
                id="news-industry"
                name="news-industry"
                value={industry}
                onChange={(event) => setIndustry(event.target.value)}
                className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
              >
                <option value="all">All</option>
                {industryOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="news-limit" className="text-xs text-slate-300">
                Limit
              </label>
              <input
                id="news-limit"
                name="news-limit"
                type="number"
                min={5}
                max={100}
                value={limit}
                onChange={(event) => {
                  const raw = Number(event.target.value);
                  if (!Number.isFinite(raw)) {
                    setLimit(25);
                    return;
                  }
                  const clamped = Math.max(5, Math.min(100, raw));
                  setLimit(clamped);
                }}
                className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
              />
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4 items-end">
            <div className="lg:col-span-2">
              <label htmlFor="news-tickers" className="text-xs text-slate-300">
                Ticker Focus (comma-separated)
              </label>
              <input
                id="news-tickers"
                name="news-tickers"
                value={tickers}
                onChange={(event) => setTickers(event.target.value)}
                className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                placeholder="AAPL, MSFT, XOM"
              />
            </div>
            <button
              type="button"
              onClick={() => setForceToken((prev) => prev + 1)}
              className="rounded-xl border border-green-400/70 px-4 py-2 text-xs text-green-200"
            >
              Refresh News Now
            </button>
          </div>
          {sourceOptions.length ? (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-200">Sources</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {sourceOptions.map((source) => (
                  <button
                    key={source}
                    type="button"
                    onClick={() => toggleSource(source)}
                    className={`rounded-full border px-3 py-1 text-[11px] ${
                      sources.includes(source)
                        ? "border-green-400/70 text-green-200"
                        : "border-slate-700 text-slate-300"
                    }`}
                  >
                    {source}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </Collapsible>

        <div className="rounded-xl border border-slate-700 p-4">
          <p className="text-xs font-semibold text-slate-200 mb-2">Feed Health</p>
          <p className="text-sm text-green-300">{data?.cached ? "Cached feed" : "Live fetch"}</p>
          {data?.skipped?.length ? (
            <p className="text-xs text-amber-300 mt-2">Skipped: {data.skipped.join(", ")}</p>
          ) : (
            <p className="text-xs text-slate-400 mt-2">No sources skipped.</p>
          )}
          {data?.health ? (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-300">
              {Object.entries(data.health).map(([source, health]) => (
                <div key={source} className="rounded-lg border border-slate-800/60 p-2">
                  <p className="text-slate-100">{source}</p>
                  <p>Failures: {health.fail_count ?? 0}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        {items.length === 0 ? (
          <p>No articles match the current scope. Open Filters to broaden the search, or refresh the feed.</p>
        ) : (
          items.map((item) => (
            <div key={`${item.title}-${item.source}`} className="border-b border-slate-800/60 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-slate-100 font-medium">{item.title}</p>
                {item.published_ts ? (
                  <p className="text-[11px] text-slate-400">
                    {formatAge(item.published_ts)}
                  </p>
                ) : null}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-300">
                <span>{formatSources(item)}</span>
                {item.published_ts ? (
                  <span>{formatTimestamp(item.published_ts)}</span>
                ) : null}
              </div>
              {item.sources && item.sources.length > 1 ? (
                <p className="mt-1 text-[11px] text-slate-400">
                  Deduped across feeds: {item.sources.join(" • ")}
                </p>
              ) : null}
              {(item.regions?.length || item.industries?.length || item.tags?.length) ? (
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-300">
                  {(item.regions || []).slice(0, 2).map((region) => (
                    <span key={`region-${region}`} className="rounded-full border border-slate-700 px-2 py-0.5">
                      {region}
                    </span>
                  ))}
                  {(item.industries || []).slice(0, 2).map((industry) => (
                    <span key={`industry-${industry}`} className="rounded-full border border-slate-700 px-2 py-0.5">
                      {industry}
                    </span>
                  ))}
                  {(item.tags || []).slice(0, 3).map((tag) => (
                    <span key={`tag-${tag}`} className="rounded-full border border-slate-700 px-2 py-0.5">
                      {tag}
                    </span>
                  ))}
                </div>
              ) : null}
              {item.url && (
                <a className="mt-2 inline-flex text-xs text-green-300" href={item.url} target="_blank" rel="noreferrer">
                  Open source
                </a>
              )}
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
