import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Label,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Card } from "../components/ui/Card";
import { Collapsible } from "../components/ui/Collapsible";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { KpiCard } from "../components/ui/KpiCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { useApi } from "../lib/api";

type EmotionSeriesPoint = {
  label: string;
  emotions: Record<string, number>;
};

type Hotspot = {
  region?: string;
  score?: number;
  article_count?: number;
  event_counts?: Record<string, number>;
  impact_channels?: Record<string, number>;
  affected_industries?: string[];
  provenance?: {
    source_mode?: string;
  };
};

type IntelReport = {
  title?: string;
  summary?: string[];
  sections?: { title: string; rows: string[][] }[];
  risk_level?: string;
  risk_score?: number;
  confidence?: string | null;
  support?: {
    summary?: string;
  };
  risk_series?: { label: string; value: number }[];
  hotspots?: Hotspot[];
  event_counts?: Record<string, number>;
  impact_counts?: Record<string, number>;
  news?: {
    count?: number;
    risk_score?: number | null;
    sentiment_avg?: number;
    negative_ratio?: number;
    category_counts?: Record<string, number>;
    event_counts?: Record<string, number>;
    impact_counts?: Record<string, number>;
    emotion_counts?: Record<string, number>;
    region_counts?: Record<string, number>;
    subregion_counts?: Record<string, Record<string, number>>;
    region_emotion_counts?: Record<string, Record<string, number>>;
    industry_emotion_counts?: Record<string, Record<string, number>>;
    region_industry_emotion_counts?: Record<string, Record<string, Record<string, number>>>;
    timestamp_ratio?: number;
    emotion_series?: EmotionSeriesPoint[];
  };
};

type IntelMeta = {
  regions: { name: string; industries: string[] }[];
  industries: string[];
  categories: string[];
  sources: string[];
};

function formatLabel(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function rankedEntries(record?: Record<string, number>) {
  return Object.entries(record || {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function topCountsLabel(record?: Record<string, number>, limit = 4) {
  return rankedEntries(record)
    .slice(0, limit)
    .map(([key, count]) => `${formatLabel(key)} ${count}`)
    .join(" • ");
}

export default function Intel() {
  const { data: meta, error: metaError } = useApi<IntelMeta>("/api/intel/meta", {
    interval: 600000
  });
  const [region, setRegion] = useState("Global");
  const [industry, setIndustry] = useState("all");
  const [categories, setCategories] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [fusionOpen, setFusionOpen] = useState(true);
  const [weatherOpen, setWeatherOpen] = useState(false);
  const [conflictOpen, setConflictOpen] = useState(false);

  const categoriesParam = categories.length ? `&categories=${encodeURIComponent(categories.join(","))}` : "";
  const sourcesParam = sources.length ? `&sources=${encodeURIComponent(sources.join(","))}` : "";
  const intelQuery = useMemo(
    () =>
      `/api/intel/summary?region=${encodeURIComponent(region)}&industry=${encodeURIComponent(industry)}${categoriesParam}${sourcesParam}`,
    [region, industry, categoriesParam, sourcesParam]
  );
  const weatherQuery = useMemo(
    () => `/api/intel/weather?region=${encodeURIComponent(region)}&industry=${encodeURIComponent(industry)}`,
    [region, industry]
  );
  const conflictQuery = useMemo(
    () =>
      `/api/intel/conflict?region=${encodeURIComponent(region)}&industry=${encodeURIComponent(industry)}${categoriesParam}${sourcesParam}`,
    [region, industry, categoriesParam, sourcesParam]
  );
  const { data, error: summaryError, refresh } = useApi<IntelReport>(intelQuery, {
    interval: 60000
  });
  const { data: weather, error: weatherError } = useApi<IntelReport>(weatherQuery, {
    interval: 120000
  });
  const { data: conflict, error: conflictError } = useApi<IntelReport>(conflictQuery, {
    interval: 120000
  });

  const authHint = "Check LOTBOOK_WEB_API_KEY + localStorage lotbook_api_key.";
  const errorMessages = [
    metaError ? `Intel metadata failed: ${metaError}` : null,
    summaryError
      ? `Summary failed: ${summaryError}${summaryError.includes("401") || summaryError.includes("403") ? ` (${authHint})` : ""}`
      : null,
    weatherError ? `Weather failed: ${weatherError}` : null,
    conflictError ? `Conflict failed: ${conflictError}` : null
  ].filter(Boolean) as string[];

  const regionOptions = meta?.regions?.map((entry) => entry.name) || ["Global"];
  const industryOptions = meta?.industries || ["all"];

  const toggleCategory = (value: string) => {
    setCategories((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  };
  const toggleSource = (value: string) => {
    setSources((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  };

  const categoryMix = useMemo(() => rankedEntries(data?.news?.category_counts), [data?.news?.category_counts]);
  const contextMix = useMemo(() => rankedEntries(data?.news?.event_counts), [data?.news?.event_counts]);
  const impactMix = useMemo(() => rankedEntries(data?.news?.impact_counts), [data?.news?.impact_counts]);
  const emotionMix = useMemo(() => rankedEntries(data?.news?.emotion_counts), [data?.news?.emotion_counts]);
  const regionMix = useMemo(() => rankedEntries(data?.news?.region_counts), [data?.news?.region_counts]);

  const subregionMix = useMemo(() => {
    const entries = Object.entries(data?.news?.subregion_counts || {});
    const flat: Array<[string, number]> = [];
    entries.forEach(([regionName, industries]) => {
      Object.entries(industries || {}).forEach(([industryName, count]) => {
        flat.push([`${regionName} / ${formatLabel(industryName)}`, count]);
      });
    });
    return flat.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [data?.news?.subregion_counts]);

  const regionEmotionMatrix = useMemo(() => {
    return Object.entries(data?.news?.region_emotion_counts || {})
      .map(([regionName, counts]) => {
        const ranked = rankedEntries(counts);
        const total = ranked.reduce((sum, [, count]) => sum + count, 0);
        return {
          name: regionName,
          dominant: ranked[0]?.[0] || "none",
          dominantCount: ranked[0]?.[1] || 0,
          total,
        };
      })
      .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  }, [data?.news?.region_emotion_counts]);

  const industryEmotionMatrix = useMemo(() => {
    return Object.entries(data?.news?.industry_emotion_counts || {})
      .map(([industryName, counts]) => {
        const ranked = rankedEntries(counts);
        const total = ranked.reduce((sum, [, count]) => sum + count, 0);
        return {
          name: industryName,
          dominant: ranked[0]?.[0] || "none",
          dominantCount: ranked[0]?.[1] || 0,
          total,
        };
      })
      .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  }, [data?.news?.industry_emotion_counts]);

  const topEmotions = useMemo(() => emotionMix.slice(0, 3).map(([name]) => name), [emotionMix]);

  const emotionSeries = useMemo(() => {
    const series = data?.news?.emotion_series || [];
    if (!series.length || !topEmotions.length) {
      return [];
    }
    return series.map((entry) => {
      const row: Record<string, number | string> = { label: entry.label };
      topEmotions.forEach((emotion) => {
        row[emotion] = entry.emotions?.[emotion] || 0;
      });
      return row;
    });
  }, [data?.news?.emotion_series, topEmotions]);

  const conflictContextMix = useMemo(() => rankedEntries(conflict?.event_counts), [conflict?.event_counts]);
  const conflictImpactMix = useMemo(() => rankedEntries(conflict?.impact_counts), [conflict?.impact_counts]);

  const timestampCoverage = data?.news?.timestamp_ratio ?? 0;
  const showTrendData = timestampCoverage >= 0.2 && (data?.risk_series || []).length > 0;

  const renderRows = (rows?: (string[] | string)[]) => {
    if (!rows || rows.length === 0) {
      return <p className="text-xs text-slate-500">No detail rows available.</p>;
    }
    return (
      <div className="space-y-2 text-xs text-slate-300">
        {rows.map((row, idx) => {
          if (Array.isArray(row)) {
            const [label, value] = row;
            return (
              <div key={`${label}-${idx}`} className="flex items-start justify-between gap-4">
                <span className="text-slate-400">{label}</span>
                <span className="text-right text-slate-200">{value || "-"}</span>
              </div>
            );
          }
          return (
            <p key={`${row}-${idx}`} className="text-slate-300">
              {row}
            </p>
          );
        })}
      </div>
    );
  };

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader label="INTEL" title="Global Impact Summary" right={data?.risk_level ?? "Loading"} />
      <div className="mt-4">
        <ErrorBanner messages={errorMessages} onRetry={refresh} />
      </div>
      <div className="mt-6 space-y-4 text-sm text-slate-300">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard label="Risk Level" value={data?.risk_level || "Loading"} tone="text-green-300" />
          <KpiCard
            label="Risk Score"
            value={data?.risk_score !== undefined ? `${data.risk_score}/10` : "?"}
            tone="text-slate-100"
          />
          <KpiCard label="Data Support" value={data?.support?.summary || "?"} tone="text-slate-100" />
        </div>

        <Collapsible
          title="Filters"
          meta={`${region} / ${industry}`}
          open={filtersOpen}
          onToggle={() => setFiltersOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div>
              <label htmlFor="intel-region" className="text-xs text-slate-300">
                Region
              </label>
              <select
                id="intel-region"
                name="intel-region"
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
              <label htmlFor="intel-industry" className="text-xs text-slate-300">
                Industry
              </label>
              <select
                id="intel-industry"
                name="intel-industry"
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
              <p className="text-xs font-semibold text-slate-200">Contexts / Channels</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(meta?.categories || []).map((category) => (
                  <button
                    key={category}
                    type="button"
                    onClick={() => toggleCategory(category)}
                    className={`rounded-full border px-3 py-1 text-[11px] ${
                      categories.includes(category)
                        ? "border-green-400/70 text-green-200"
                        : "border-slate-700 text-slate-300"
                    }`}
                  >
                    {formatLabel(category)}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="mt-4">
            <p className="text-xs font-semibold text-slate-200">Sources</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(meta?.sources || []).map((source) => (
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
        </Collapsible>

        <Collapsible
          title="Combined Overview"
          meta={data?.title || "Global Impact Report"}
          open={fusionOpen}
          onToggle={() => setFusionOpen((prev) => !prev)}
        >
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Summary</p>
              <div className="space-y-2">
                {(data?.summary || ["No intel payload yet."]).map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Global Signal Trend</p>
                <p className="mb-3 text-[11px] leading-4 text-slate-400">
                  Shows how the combined source-backed signal score changes over the available observation windows.
                </p>
                {showTrendData ? (
                  <div className="h-40 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data?.risk_series} margin={{ top: 4, right: 8, bottom: 26, left: 8 }}>
                        <defs>
                          <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--green-500)" stopOpacity={0.6} />
                            <stop offset="95%" stopColor="var(--slate-900)" stopOpacity={0.1} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="var(--slate-700)" strokeDasharray="3 3" />
                        <XAxis dataKey="label" tick={{ fill: "var(--slate-100)", fontSize: 10 }}>
                          <Label value="Observation Window" position="insideBottom" offset={-16} fill="var(--slate-200)" />
                        </XAxis>
                        <YAxis tick={{ fill: "var(--slate-100)", fontSize: 10 }} domain={[0, 10]}>
                          <Label
                            value="Signal Score (0-10)"
                            angle={-90}
                            position="insideLeft"
                            style={{ textAnchor: "middle" }}
                            fill="var(--slate-200)"
                          />
                        </YAxis>
                        <Tooltip
                          formatter={(value) => [Number(value).toFixed(2), "Global signal score"]}
                          labelFormatter={(label) => `Observation window: ${label}`}
                          contentStyle={{
                            background: "var(--slate-900)",
                            borderRadius: 8,
                            borderColor: "var(--slate-700)"
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="value"
                          stroke="var(--green-500)"
                          fill="url(#riskFill)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">Time trend unavailable (missing timestamps).</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Emotion Trend</p>
                <p className="mb-3 text-[11px] leading-4 text-slate-400">
                  Shows counts of classified article emotions by observation window. Counts are not sentiment probabilities.
                </p>
                {showTrendData && emotionSeries.length > 0 ? (
                  <div className="h-40 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={emotionSeries} margin={{ top: 4, right: 8, bottom: 26, left: 8 }}>
                        <CartesianGrid stroke="var(--slate-700)" strokeDasharray="3 3" />
                        <XAxis dataKey="label" tick={{ fill: "var(--slate-100)", fontSize: 10 }}>
                          <Label value="Observation Window" position="insideBottom" offset={-16} fill="var(--slate-200)" />
                        </XAxis>
                        <YAxis tick={{ fill: "var(--slate-100)", fontSize: 10 }}>
                          <Label
                            value="Classified Articles"
                            angle={-90}
                            position="insideLeft"
                            style={{ textAnchor: "middle" }}
                            fill="var(--slate-200)"
                          />
                        </YAxis>
                        <Tooltip
                          formatter={(value, name) => [Number(value).toLocaleString(), formatLabel(String(name))]}
                          labelFormatter={(label) => `Observation window: ${label}`}
                          contentStyle={{
                            background: "var(--slate-900)",
                            borderRadius: 8,
                            borderColor: "var(--slate-700)"
                          }}
                        />
                        {topEmotions.map((emotion, index) => (
                          <Bar
                            key={emotion}
                            dataKey={emotion}
                            stackId="emotion"
                            fill={
                              index === 0
                                ? "var(--green-400)"
                                : index === 1
                                  ? "var(--green-300)"
                                  : "var(--green-200)"
                            }
                          />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">Time trend unavailable (missing timestamps).</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Context Mix</p>
                {contextMix.length > 0 ? (
                  <div className="space-y-2 text-xs text-slate-100">
                    {contextMix.slice(0, 6).map(([context, count]) => (
                      <div key={context} className="flex items-center justify-between">
                        <span className="text-slate-300">{formatLabel(context)}</span>
                        <span className="text-slate-100">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">No context mix available yet.</p>
                )}
                {impactMix.length > 0 ? (
                  <div className="mt-4 space-y-2 text-xs text-slate-100">
                    <p className="text-xs font-semibold text-slate-200">Impacted Channels</p>
                    {impactMix.slice(0, 6).map(([channel, count]) => (
                      <div key={channel} className="flex items-center justify-between">
                        <span className="text-slate-300">{formatLabel(channel)}</span>
                        <span className="text-slate-100">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {emotionMix.length > 0 ? (
                  <div className="mt-4 space-y-2 text-xs text-slate-100">
                    <p className="text-xs font-semibold text-slate-200">Emotion Mix</p>
                    {emotionMix.slice(0, 6).map(([emotion, count]) => (
                      <div key={emotion} className="flex items-center justify-between">
                        <span className="text-slate-300">{formatLabel(emotion)}</span>
                        <span className="text-slate-100">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
                {categoryMix.length > 0 ? (
                  <div className="mt-4 space-y-2 text-xs text-slate-100">
                    <p className="text-xs font-semibold text-slate-200">Topic Mix</p>
                    {categoryMix.slice(0, 5).map(([topic, count]) => (
                      <div key={topic} className="flex items-center justify-between">
                        <span className="text-slate-300">{formatLabel(topic)}</span>
                        <span className="text-slate-100">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Regional Coverage</p>
                {regionMix.length > 0 ? (
                  <div className="space-y-2 text-xs text-slate-100">
                    {regionMix.slice(0, 6).map(([regionName, count]) => (
                      <div key={regionName} className="flex items-center justify-between">
                        <span className="text-slate-300">{regionName}</span>
                        <span className="text-slate-100">{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">No regional coverage data yet.</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Regional Emotion Matrix</p>
                {regionEmotionMatrix.length > 0 ? (
                  <div className="space-y-2 text-xs text-slate-100">
                    {regionEmotionMatrix.slice(0, 6).map((entry) => (
                      <div key={entry.name} className="flex items-center justify-between gap-4">
                        <span className="text-slate-300">{entry.name}</span>
                        <span className="text-right text-slate-100">
                          {formatLabel(entry.dominant)} ({entry.dominantCount}/{entry.total})
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">No regional emotion data yet.</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Industry Emotion Matrix</p>
                {industryEmotionMatrix.length > 0 ? (
                  <div className="space-y-2 text-xs text-slate-100">
                    {industryEmotionMatrix.slice(0, 6).map((entry) => (
                      <div key={entry.name} className="flex items-center justify-between gap-4">
                        <span className="text-slate-300">{formatLabel(entry.name)}</span>
                        <span className="text-right text-slate-100">
                          {formatLabel(entry.dominant)} ({entry.dominantCount}/{entry.total})
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">No industry emotion data yet.</p>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Subregional Coverage</p>
              {subregionMix.length > 0 ? (
                <div className="space-y-2 text-xs text-slate-100">
                  {subregionMix.slice(0, 8).map(([label, count]) => (
                    <div key={label} className="flex items-center justify-between">
                      <span className="text-slate-300">{label}</span>
                      <span className="text-slate-100">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">No subregional coverage data yet.</p>
              )}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {(data?.sections || []).slice(0, 4).map((section) => (
                <div key={section.title} className="rounded-xl border border-slate-700 p-4">
                  <p className="text-xs font-semibold text-slate-200 mb-2">{section.title}</p>
                  {renderRows(section.rows as (string[] | string)[])}
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">News Metrics</p>
              {renderRows([
                ["Articles", String(data?.news?.count ?? 0)],
                ["Sentiment avg", String(data?.news?.sentiment_avg ?? 0)],
                ["Negative ratio", String(data?.news?.negative_ratio ?? 0)],
                ["Conflict context", String(data?.news?.event_counts?.conflict ?? 0)],
                [
                  "News risk score",
                  data?.news?.risk_score !== undefined && data?.news?.risk_score !== null
                    ? `${data?.news?.risk_score}/10`
                    : "Unavailable"
                ],
              ])}
            </div>
          </div>
        </Collapsible>

        <Collapsible
          title="Weather Data"
          meta={weather?.risk_level || "Loading"}
          open={weatherOpen}
          onToggle={() => setWeatherOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Summary</p>
              {(weather?.summary || ["No weather payload yet."]).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
            {(weather?.sections || []).map((section) => (
              <div key={section.title} className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">{section.title}</p>
                {renderRows(section.rows as (string[] | string)[])}
              </div>
            ))}
          </div>
        </Collapsible>

        <Collapsible
          title="Conflict Data"
          meta={conflict?.risk_level || "Loading"}
          open={conflictOpen}
          onToggle={() => setConflictOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Summary</p>
              {(conflict?.summary || ["No conflict payload yet."]).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>

            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Regional Conflict Signals</p>
              {conflict?.hotspots && conflict.hotspots.length > 0 ? (
                <div className="space-y-3 text-xs text-slate-100">
                  {conflict.hotspots.slice(0, 4).map((hotspot, index) => (
                    <div
                      key={`${hotspot.region || "hotspot"}-${index}`}
                      className="rounded-lg border border-slate-800 p-3"
                    >
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-slate-200">{hotspot.region || "Region"}</span>
                        <span className="text-slate-100">
                          {hotspot.score !== undefined ? `${hotspot.score}/10` : "n/a"} • {hotspot.article_count || 0} articles
                        </span>
                      </div>
                      <p className="mt-2 text-slate-400">
                        {topCountsLabel(hotspot.event_counts, 3) || "No event tags"}
                      </p>
                      <p className="mt-1 text-slate-500">
                        {topCountsLabel(hotspot.impact_channels, 3) || "No impacted channels"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">No regional conflict signals available yet.</p>
              )}
            </div>

            {conflictContextMix.length > 0 ? (
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Conflict Context Mix</p>
                <div className="space-y-2 text-xs text-slate-100">
                  {conflictContextMix.slice(0, 6).map(([context, count]) => (
                    <div key={context} className="flex items-center justify-between">
                      <span className="text-slate-300">{formatLabel(context)}</span>
                      <span className="text-slate-100">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {conflictImpactMix.length > 0 ? (
              <div className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">Impacted Markets</p>
                <div className="space-y-2 text-xs text-slate-100">
                  {conflictImpactMix.slice(0, 6).map(([channel, count]) => (
                    <div key={channel} className="flex items-center justify-between">
                      <span className="text-slate-300">{formatLabel(channel)}</span>
                      <span className="text-slate-100">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {(conflict?.sections || []).map((section) => (
              <div key={section.title} className="rounded-xl border border-slate-700 p-4">
                <p className="text-xs font-semibold text-slate-200 mb-2">{section.title}</p>
                {renderRows(section.rows as (string[] | string)[])}
              </div>
            ))}
          </div>
        </Collapsible>
      </div>
    </Card>
  );
}
