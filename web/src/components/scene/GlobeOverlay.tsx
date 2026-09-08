import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import {
  Html,
  Line,
  OrbitControls,
  PerformanceMonitor,
  Stars
} from "@react-three/drei";
import type { Mesh } from "three";
import * as THREE from "three";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Eye,
  FilterX,
  List,
  Orbit,
  RadioTower,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { apiGet, useApi } from "../../lib/api";
import {
  buildGlobeContextCanvas,
  loadGlobeGeography,
  type GlobeGeographyData,
} from "../../lib/globeGeography";
import {
  type IntelSceneLens,
  type SceneId,
  type SceneCameraPreset,
  type TrackerSceneMode,
  useSceneController
} from "../../lib/scene";
import { useReducedMotionPreference } from "../../lib/useReducedMotion";
import { GlobeDataDensity } from "./GlobeDataDensity";

type SceneFeature = {
  id: string;
  layer: string;
  source?: string;
  geometry: {
    type: "Point" | "LineString" | "Polygon" | "MultiPolygon";
    coordinates: number[] | number[][] | number[][][] | number[][][][];
  };
  ts?: number | null;
  properties?: Record<string, unknown>;
  confidence?: number | null;
  freshness?: {
    age_sec?: number | null;
    state?: string | null;
    is_stale?: boolean;
  };
  warnings?: string[];
};

type SceneLayer = {
  id: string;
  kind: "point" | "path" | "pulse" | "area";
  label: string;
  features: SceneFeature[];
  style_hints?: Record<string, unknown>;
  time_bounds?: {
    start_ts?: number | null;
    end_ts?: number | null;
  };
  legend?: Array<{
    label?: string;
    value?: string;
    color?: string;
  }>;
  filters?: Record<string, unknown>;
  meta?: {
    count?: number;
    warnings?: string[];
  };
};

type FocusTarget = {
  id: string;
  label?: string;
  domain?: string;
  kind?: string;
  category?: string;
  lat?: number | null;
  lon?: number | null;
  confidence?: number | null;
};

type ScenePayload = {
  scene_id: string;
  title: string;
  kind: string;
  camera_defaults?: {
    target_lat?: number;
    target_lon?: number;
    distance?: number;
  };
  timeline?: {
    mode?: string;
    point_count?: number;
    trail_count?: number;
    start_ts?: number | null;
    end_ts?: number | null;
  };
  layers: SceneLayer[];
  focus_targets: FocusTarget[];
  meta?: {
    timestamp?: number;
    available_lenses?: string[];
    available_overlays?: string[];
    warnings?: string[];
  };
};

type IntelMeta = {
  categories: string[];
  industries: string[];
  regions: Array<{ industries: string[]; name: string }>;
  sources: string[];
};

type ClientSummary = {
  client_id: string;
  name: string;
  risk_profile?: string;
  accounts_count?: number;
  holdings_count?: number;
};

type ClientIndex = {
  clients?: ClientSummary[];
};

type TrackerPresentationPresetId =
  | "operations-overview"
  | "air-picture"
  | "maritime-picture"
  | "lead-signal";

type IntelPresentationPresetId =
  | "global-risk"
  | "weather-watch"
  | "conflict-watch"
  | "news-pressure"
  | "emotion-watch";

type PresentationPresetId = TrackerPresentationPresetId | IntelPresentationPresetId;

const TRACKER_MODE_OPTIONS: Array<{ id: TrackerSceneMode; label: string }> = [
  { id: "combined", label: "Combined" },
  { id: "flights", label: "Flights" },
  { id: "ships", label: "Ships" }
];

const INTEL_LENS_OPTIONS: Array<{ id: IntelSceneLens; label: string }> = [
  { id: "combined", label: "Combined" },
  { id: "weather", label: "Weather" },
  { id: "conflict", label: "Conflict" },
  { id: "news", label: "News" },
  { id: "emotion", label: "Emotion" }
];

const CAMERA_PRESET_OPTIONS: Array<{ id: SceneCameraPreset; label: string }> = [
  { id: "free", label: "Free Orbit" },
  { id: "overview", label: "Overview" },
  { id: "focus", label: "Follow Selection" }
];

const GLOBE_RADIUS = 1.6;
const SCENE_ROTATION_VALUES: [number, number, number] = [0.15, 0.3, 0];
const SCENE_ROTATION = new THREE.Euler(...SCENE_ROTATION_VALUES);
const TOUR_INTERVAL_MS = 3600;

const TRACKER_PRESENTATION_PRESETS: Array<{
  id: TrackerPresentationPresetId;
  label: string;
}> = [
  { id: "operations-overview", label: "Ops Overview" },
  { id: "air-picture", label: "Air Picture" },
  { id: "maritime-picture", label: "Sea Picture" },
  { id: "lead-signal", label: "Lead Signal" }
];

const INTEL_PRESENTATION_PRESETS: Array<{
  id: IntelPresentationPresetId;
  label: string;
}> = [
  { id: "global-risk", label: "Global Signals" },
  { id: "weather-watch", label: "Weather Watch" },
  { id: "conflict-watch", label: "Conflict Signals" },
  { id: "news-pressure", label: "News Signals" },
  { id: "emotion-watch", label: "Emotion Watch" }
];

function latLonToVector(
  lat: number,
  lon: number,
  radius = GLOBE_RADIUS,
  altitude = 0
): THREE.Vector3 {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  const r = radius + altitude;
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

function formatTimestamp(ts?: number | null) {
  if (!ts) return "Live";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(ts * 1000));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function getNumericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function getFreshnessAge(feature: SceneFeature) {
  const age = feature.freshness?.age_sec;
  return typeof age === "number" && Number.isFinite(age) ? age : Number.MAX_SAFE_INTEGER;
}

function getFeatureConfidence(feature: SceneFeature) {
  return typeof feature.confidence === "number" && Number.isFinite(feature.confidence)
    ? feature.confidence
    : 0;
}

function getTrackerKind(feature: SceneFeature) {
  const properties = asRecord(feature.properties);
  return String(properties?.kind || "");
}

function getTrackerSpeedHeat(feature: SceneFeature) {
  return getNumericValue(asRecord(feature.properties)?.speed_heat) || 0;
}

function getFeatureNewsCount(feature: SceneFeature) {
  return getNumericValue(asRecord(asRecord(feature.properties)?.news)?.count) || 0;
}

function getFeatureCoordinates(feature: SceneFeature) {
  const coords = Array.isArray(feature.geometry.coordinates)
    ? (feature.geometry.coordinates as number[])
    : [];
  if (coords.length < 2) return null;
  return { lon: Number(coords[0]), lat: Number(coords[1]) };
}

function formatCoordinate(value: number | null | undefined, axis: "lat" | "lon") {
  if (!Number.isFinite(value)) return "n/a";
  const absolute = Math.abs(Number(value));
  const suffix = axis === "lat"
    ? (Number(value) >= 0 ? "N" : "S")
    : (Number(value) >= 0 ? "E" : "W");
  return `${absolute.toFixed(3)}° ${suffix}`;
}

function formatMetricValue(value: unknown, suffix = "") {
  const numeric = getNumericValue(value);
  if (numeric === null) return "n/a";
  const rounded = Math.abs(numeric) >= 100 ? Math.round(numeric).toString() : numeric.toFixed(1);
  return `${rounded}${suffix}`;
}

function formatDisplayLabel(value: unknown) {
  if (typeof value !== "string" || !value.trim()) return "n/a";
  return value
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatRatioAsPercent(value: unknown) {
  const numeric = getNumericValue(value);
  if (numeric === null) return "n/a";
  return `${(numeric * 100).toFixed(numeric < 0.1 ? 1 : 0)}%`;
}

function formatAge(ageSec?: number | null, state?: string | null) {
  if (!Number.isFinite(ageSec)) {
    return state ? formatDisplayLabel(state) : "n/a";
  }
  const seconds = Math.max(0, Math.round(Number(ageSec)));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(seconds < 21600 ? 1 : 0)}h`;
}

function formatDuration(value: unknown) {
  const numeric = getNumericValue(value);
  if (numeric === null) return "n/a";
  const seconds = Math.max(0, Math.round(numeric));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(seconds < 21600 ? 1 : 0)} hr`;
}

function sumRecordValues(record: Record<string, unknown> | null) {
  if (!record) return 0;
  return Object.values(record).reduce<number>((total, value) => {
    const numeric = getNumericValue(value);
    return total + (numeric ?? 0);
  }, 0);
}

function formatStringList(values: unknown, limit = 4) {
  if (!Array.isArray(values)) return "n/a";
  const entries = values
    .filter((value): value is string => typeof value === "string" && Boolean(value.trim()))
    .map((value) => value.trim());
  if (!entries.length) return "n/a";
  return entries.slice(0, limit).join(", ");
}

function formatOptionalText(value: unknown) {
  if (typeof value !== "string" || !value.trim()) return "n/a";
  return value.trim();
}

function formatFeatureSource(feature: SceneFeature) {
  if (typeof feature.source === "string" && feature.source.trim()) {
    return formatDisplayLabel(feature.source);
  }
  return "n/a";
}

function formatCoverage(record: Record<string, unknown> | null) {
  if (!record) return "n/a";
  const entries = Object.entries(record)
    .filter(([, value]) => typeof value === "boolean")
    .map(([key, value]) => `${formatDisplayLabel(key)} ${value ? "available" : "unavailable"}`);
  return entries.length ? entries.join(" • ") : "n/a";
}

function formatTopCountList(record: Record<string, unknown> | null, limit = 4) {
  return getTopEntries(record, limit)
    .map(([label, count]) => `${formatDisplayLabel(label)} (${Math.round(Number(count))})`)
    .join(" • ") || "n/a";
}

function getTopEntries(record: Record<string, unknown> | null, limit = 3) {
  if (!record) return [];
  return Object.entries(record)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .slice(0, limit);
}

function getDominantEmotion(feature: SceneFeature) {
  const emotion = asRecord(asRecord(feature.properties)?.emotion);
  if (typeof emotion?.dominant === "string" && emotion.dominant.trim()) {
    return emotion.dominant.trim();
  }
  const news = asRecord(asRecord(feature.properties)?.news);
  const top = getTopEntries(asRecord(news?.emotion_counts), 1)[0];
  return top ? top[0] : "neutral";
}

function getEmotionObservationCount(feature: SceneFeature) {
  const emotion = asRecord(asRecord(feature.properties)?.emotion);
  const emotionCount = getNumericValue(emotion?.count);
  if (emotionCount !== null) {
    return emotionCount;
  }
  const news = asRecord(asRecord(feature.properties)?.news);
  return sumRecordValues(asRecord(news?.emotion_counts));
}

function getEmotionAccent(emotion: string) {
  const normalized = emotion.toLowerCase();
  if (normalized.includes("anger")) return "#ff7b72";
  if (normalized.includes("fear")) return "#ffb36b";
  if (normalized.includes("sad")) return "#83a5ff";
  if (normalized.includes("joy") || normalized.includes("positive")) return "#7dffd3";
  if (normalized.includes("trust") || normalized.includes("calm")) return "#75d7ff";
  return "#d5ddff";
}

function getLensLabel(lens: IntelSceneLens) {
  return INTEL_LENS_OPTIONS.find((option) => option.id === lens)?.label || "Combined";
}

function getFeatureLabel(feature: SceneFeature) {
  const properties = asRecord(feature.properties);
  return String(properties?.label || properties?.region || feature.id);
}

function getFeatureLensScore(feature: SceneFeature, lens: IntelSceneLens): number | null {
  const properties = asRecord(feature.properties);
  if (!properties) return null;
  if (lens === "combined") {
    return getNumericValue(asRecord(properties.combined_risk)?.score);
  }
  if (lens === "emotion") {
    return getEmotionObservationCount(feature);
  }
  if (lens === "news") {
    const news = asRecord(properties.news);
    return getNumericValue(news?.score) ?? getNumericValue(news?.risk_score);
  }
  return getNumericValue(asRecord(properties[lens])?.score);
}

function getPulseChannel(feature: SceneFeature): string {
  const properties = asRecord(feature.properties);
  const channel = String(properties?.channel || properties?.category || "").toLowerCase();
  if (channel === "weather" || channel === "conflict" || channel === "news" || channel === "emotion") {
    return channel;
  }
  if (String(feature.layer || "").includes("conflict")) return "conflict";
  return "combined";
}

function pulseMatchesLens(feature: SceneFeature, intelLens: IntelSceneLens): boolean {
  if (intelLens === "combined") return true;
  return getPulseChannel(feature) === intelLens;
}

function pulseAccent(feature: SceneFeature): string {
  const channel = getPulseChannel(feature);
  if (channel === "weather") return "#75d7ff";
  if (channel === "news") return "#ffd166";
  if (channel === "emotion") return "#c084fc";
  return "#ff5c6a";
}

function getConflictPriority(feature: SceneFeature) {
  const properties = asRecord(feature.properties);
  const conflict = asRecord(properties?.conflict);
  const news = asRecord(properties?.news);
  const conflictScore = getNumericValue(conflict?.score);
  const articleCount = getNumericValue(conflict?.count);
  const eventCounts = {
    ...(asRecord(news?.event_counts) || {}),
    ...(asRecord(conflict?.event_counts) || {}),
  };
  const conflictEventCount = [
    "conflict",
    "war",
    "attack",
    "strike",
    "missile",
    "drone",
    "shelling",
    "military",
    "protest",
  ].reduce((total, key) => total + (getNumericValue(eventCounts[key]) || 0), 0);
  const priority = Math.max(
    conflictScore !== null ? conflictScore / 10 : 0,
    articleCount !== null ? articleCount / 20 : 0,
    conflictEventCount / 8
  );
  return {
    active: Boolean(
      (conflictScore !== null && conflictScore >= 3) ||
      (articleCount !== null && articleCount > 0) ||
      conflictEventCount > 0
    ),
    priority: Math.max(0, Math.min(1, priority)),
    score: conflictScore,
  };
}

function getFeaturePresentation(feature: SceneFeature) {
  return asRecord(asRecord(feature.properties)?.presentation);
}

function isIntelFeature(feature: SceneFeature) {
  const properties = asRecord(feature.properties);
  const kind = String(properties?.kind || "").toLowerCase();
  return (
    kind === "region" ||
    String(feature.layer || "").startsWith("regional-") ||
    Boolean(properties?.combined_risk) ||
    Boolean(properties?.news)
  );
}

function getFeatureDominantChannel(feature: SceneFeature): IntelSceneLens | "combined" {
  const dominant = getFeaturePresentation(feature)?.dominant_channel;
  if (
    dominant === "weather" ||
    dominant === "conflict" ||
    dominant === "news" ||
    dominant === "emotion" ||
    dominant === "combined"
  ) {
    return dominant;
  }
  return "combined";
}

function getFeatureIntensity(
  feature: SceneFeature,
  sceneId: SceneId,
  intelLens: IntelSceneLens
) {
  const properties = asRecord(feature.properties);
  if (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(feature))) {
    const score = getFeatureLensScore(feature, intelLens);
    const presentationIntensity = getNumericValue(getFeaturePresentation(feature)?.intensity);
    const conflictPriority = getConflictPriority(feature);
    if (intelLens === "emotion") {
      return Math.max(0.26, Math.min(1, presentationIntensity ?? 0.58));
    }
    const rawValue = score !== null ? score / 10 : presentationIntensity;
    return Math.max(
      0.26,
      Math.min(1, Math.max(rawValue ?? 0.58, conflictPriority.priority))
    );
  }
  const speedHeat = getNumericValue(properties?.speed_heat);
  return Math.max(0.25, Math.min(1, speedHeat ?? 0.55));
}

function getFeaturePeakRawValue(
  feature: SceneFeature,
  sceneId: SceneId,
  intelLens: IntelSceneLens
) {
  const properties = asRecord(feature.properties);
  if (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(feature))) {
    if (intelLens === "emotion") {
      return getEmotionObservationCount(feature) || null;
    }
    const lensScore = getFeatureLensScore(feature, intelLens);
    const conflictScore = getConflictPriority(feature).score;
    const peakScore = Math.max(lensScore || 0, conflictScore || 0);
    return peakScore > 0 ? peakScore : null;
  }
  const speedHeat = getNumericValue(properties?.speed_heat);
  return speedHeat !== null && speedHeat > 0 ? speedHeat : null;
}

function getFeatureAccent(
  feature: SceneFeature,
  sceneId: SceneId,
  intelLens: IntelSceneLens
) {
  const properties = asRecord(feature.properties);
  if (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(feature))) {
    const channel = intelLens === "combined" ? getFeatureDominantChannel(feature) : intelLens;
    if (channel === "weather") return "#75d7ff";
    if (channel === "conflict") return "#ff3b4f";
    if (channel === "news") return "#ffd166";
    if (channel === "emotion") return getEmotionAccent(getDominantEmotion(feature));
    if (getConflictPriority(feature).active) return "#ff3b4f";
    const riskScore = getFeatureLensScore(feature, "combined") ?? 0;
    return riskScore >= 7 ? "#ff5c6a" : "#48f1a6";
  }
  if (String(properties?.kind || "") === "ship") {
    const category = String(properties?.category || "").toLowerCase();
    if (category === "cargo") return "#ffd166";
    if (category === "tanker") return "#ff8b73";
    if (category === "military" || category === "government") return "#ff9ea8";
    return "#7dffd3";
  }
  const category = String(properties?.category || "").toLowerCase();
  if (category === "cargo") return "#ffd166";
  if (category === "military" || category === "government") return "#ff9ea8";
  if (category === "private") return "#75d7ff";
  return "#d2ffef";
}

function getFeatureTooltipCopy(
  feature: SceneFeature,
  sceneId: SceneId,
  intelLens: IntelSceneLens
) {
  const properties = asRecord(feature.properties);
  if (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(feature))) {
    const combinedRisk = asRecord(properties?.combined_risk);
    const level = String(combinedRisk?.level || "Unknown");
    const lensLabel = getLensLabel(intelLens);
    const lensScore = getFeatureLensScore(feature, intelLens);
    const dominant = getFeatureDominantChannel(feature);
    const activeLabel = intelLens === "combined" ? dominant : intelLens;
    const dominantEmotion = getDominantEmotion(feature);
    if (intelLens === "emotion") {
      return `Emotion observations ${lensScore !== null ? `${Math.round(lensScore)}` : "n/a"} • ${formatDisplayLabel(dominantEmotion)} • ${level}`;
    }
    return `${lensLabel} ${lensScore !== null ? `${Math.round(lensScore)}/10` : "n/a"} • ${level} • ${String(activeLabel).toUpperCase()}`;
  }
  return `${String(properties?.kind || "signal").toUpperCase()} • ${String(properties?.category || "unknown")}`;
}

function getSelectedHeadlines(feature: SceneFeature | null): Array<{ title: string; source?: string }> {
  if (!feature) return [];
  const properties = asRecord(feature.properties);
  const brief = asRecord(properties?.brief);
  const news = asRecord(properties?.news);
  const raw = (brief?.headlines || news?.headlines || []) as unknown;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      const row = asRecord(item);
      const title = String(row?.title || "").trim();
      if (!title) return null;
      return { title, source: String(row?.source || "").trim() || undefined };
    })
    .filter((item): item is { title: string; source: string | undefined } => item !== null)
    .slice(0, 3);
}

function getSelectedIntelCopy(feature: SceneFeature | null, intelLens: IntelSceneLens) {
  if (!feature) return "Choose a region to inspect the fused signal layers.";
  const properties = asRecord(feature.properties);
  const combinedRisk = asRecord(properties?.combined_risk);
  const news = asRecord(properties?.news);
  const topSignal = String(getFeaturePresentation(feature)?.top_signal || "Regional monitoring active.");
  const newsCount = Math.round(getNumericValue(news?.count) || 0);
  const level = String(combinedRisk?.level || "Unknown");
  const lensLabel = getLensLabel(intelLens);
  const lensScore = getFeatureLensScore(feature, intelLens);
  const dominantEmotion = getDominantEmotion(feature);
  if (intelLens === "emotion") {
    return `Emotion observations ${lensScore !== null ? `${Math.round(lensScore)}` : "n/a"} • ${formatDisplayLabel(dominantEmotion)} • ${newsCount} headlines. ${topSignal}`;
  }
  return `${lensLabel} ${lensScore !== null ? `${Math.round(lensScore)}/10` : "n/a"} • ${level} • ${newsCount} headlines. ${topSignal}`;
}

function getTooltipDetailLines(
  feature: SceneFeature,
  sceneId: SceneId,
  intelLens: IntelSceneLens
) {
  const properties = asRecord(feature.properties);
  const coordinates = getFeatureCoordinates(feature);
  const coordinateCopy = coordinates
    ? `${formatCoordinate(coordinates.lat, "lat")} • ${formatCoordinate(coordinates.lon, "lon")}`
    : "Coordinates unavailable";
  if (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(feature))) {
    const news = asRecord(properties?.news);
    const dominantEmotion = formatDisplayLabel(getDominantEmotion(feature));
    const newsCount = Math.round(getNumericValue(news?.count) || 0);
    return [
      coordinateCopy,
      intelLens === "emotion"
        ? `${dominantEmotion} • ${Math.round(getFeatureLensScore(feature, "emotion") || 0)} observations`
        : `${newsCount} headlines • ${formatDisplayLabel(getFeatureDominantChannel(feature))}`,
    ];
  }
  const speed = formatMetricValue(properties?.speed_kts, " kts");
  const operator = formatDisplayLabel(properties?.operator_name || properties?.operator);
  return [coordinateCopy, `${operator} • ${speed}`];
}

function rankTrackerFeatures(
  features: SceneFeature[],
  mode: TrackerSceneMode
) {
  const filtered =
    mode === "combined"
      ? features
      : features.filter((feature) =>
          mode === "flights"
            ? getTrackerKind(feature) === "flight"
            : getTrackerKind(feature) === "ship"
        );
  return [...filtered].sort((left, right) => {
    const freshnessDelta = getFreshnessAge(left) - getFreshnessAge(right);
    if (freshnessDelta !== 0) return freshnessDelta;
    const confidenceDelta = getFeatureConfidence(right) - getFeatureConfidence(left);
    if (confidenceDelta !== 0) return confidenceDelta;
    return getTrackerSpeedHeat(right) - getTrackerSpeedHeat(left);
  });
}

function rankIntelFeatures(
  features: SceneFeature[],
  lens: IntelSceneLens
) {
  return [...features].sort((left, right) => {
    const scoreDelta = (getFeatureLensScore(right, lens) || 0) - (getFeatureLensScore(left, lens) || 0);
    if (scoreDelta !== 0) return scoreDelta;
    const newsDelta = getFeatureNewsCount(right) - getFeatureNewsCount(left);
    if (newsDelta !== 0) return newsDelta;
    return getFeatureConfidence(right) - getFeatureConfidence(left);
  });
}

function getFocusOrder(
  sceneId: SceneId,
  features: SceneFeature[],
  trackerMode: TrackerSceneMode,
  intelLens: IntelSceneLens
) {
  return sceneId === "intel"
    ? rankIntelFeatures(features, intelLens)
    : rankTrackerFeatures(features, trackerMode);
}

function getDerivedPresetId(
  sceneId: SceneId,
  sceneState: { cameraPreset: SceneCameraPreset; trackerMode: TrackerSceneMode; intelLens: IntelSceneLens }
): PresentationPresetId {
  if (sceneId === "intel") {
    if (sceneState.intelLens === "weather") return "weather-watch";
    if (sceneState.intelLens === "conflict") return "conflict-watch";
    if (sceneState.intelLens === "news") return "news-pressure";
    return "global-risk";
  }
  if (sceneState.cameraPreset === "focus") return "lead-signal";
  if (sceneState.trackerMode === "flights") return "air-picture";
  if (sceneState.trackerMode === "ships") return "maritime-picture";
  return "operations-overview";
}

function getFocusTargetMeta(
  sceneId: SceneId,
  target: FocusTarget
) {
  if (sceneId === "intel" || target.domain === "intel") {
    return `${String(target.kind || "combined").toUpperCase()} • ${target.category || "Unknown"}`;
  }
  return `${String(target.kind || "signal").toUpperCase()} • ${target.category || "unknown"}`;
}

async function buildFallbackTrackerScene(mode: TrackerSceneMode): Promise<ScenePayload> {
  const snapshot = await apiGet<{
    mode?: string;
    count: number;
    warnings?: string[];
    points: Array<{
      id?: string;
      label?: string;
      kind?: string;
      category?: string;
      lat?: number;
      lon?: number;
      updated_ts?: number | null;
      speed_heat?: number | null;
      speed_kts?: number | null;
      operator?: string | null;
      operator_name?: string | null;
      country?: string | null;
    }>;
  }>(`/api/trackers/snapshot?mode=${mode}`);
  return {
    scene_id: "osint-trackers-fallback",
    title: "Trackers",
    kind: "osint",
    camera_defaults: {
      target_lat: 12,
      target_lon: 8,
      distance: 3.4
    },
    timeline: {
      mode: snapshot.mode || mode,
      point_count: snapshot.count || snapshot.points.length,
      trail_count: 0
    },
    layers: [
      {
        id: "live-trackers",
        kind: "point",
        label: "Live Trackers",
        features: snapshot.points
          .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
          .slice(0, 18)
          .map((point, index) => ({
            id: point.id || `fallback-${index}`,
            layer: "live-trackers",
            geometry: {
              type: "Point" as const,
              coordinates: [point.lon as number, point.lat as number]
            },
            ts: point.updated_ts || null,
            properties: {
              label: point.label,
              kind: point.kind,
              category: point.category,
              operator: point.operator,
              operator_name: point.operator_name,
              country: point.country,
              latitude: point.lat,
              longitude: point.lon,
              popup_coordinates: {
                lat: point.lat,
                lon: point.lon
              },
              speed_kts: point.speed_kts,
              speed_heat: point.speed_heat
            },
            confidence: null,
            freshness: {
              state: "fallback",
              age_sec: null,
              is_stale: false
            }
          })),
        meta: {
          count: snapshot.points.length,
          warnings: [
            "Scene route unavailable; using tracker snapshot fallback.",
            ...(snapshot.warnings || [])
          ]
        }
      },
      {
        id: "tracker-trails",
        kind: "path",
        label: "Tracker Trails",
        features: [],
        meta: {
          count: 0,
          warnings: ["Replay trails unavailable in fallback mode."]
        }
      }
    ],
    focus_targets: snapshot.points
      .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
      .slice(0, 6)
      .map((point, index) => ({
        id: point.id || `fallback-${index}`,
        label: point.label,
        kind: point.kind,
        category: point.category,
        lat: point.lat,
        lon: point.lon,
        confidence: null
      })),
    meta: {
      timestamp: Math.floor(Date.now() / 1000),
      warnings: [
        "Scene route unavailable; using tracker snapshot fallback.",
        ...(snapshot.warnings || [])
      ]
    }
  };
}

function AdaptiveDprController({
  qualityFactor,
  reducedMotion
}: {
  qualityFactor: number;
  reducedMotion: boolean;
}) {
  const setDpr = useThree((state) => state.setDpr);
  const initialDpr = useThree((state) => state.viewport.initialDpr);

  useEffect(() => {
    const baseDpr = Math.min(initialDpr || 1, 1.6);
    const nextDpr = reducedMotion
      ? 1
      : Math.max(0.85, Math.min(1.55, baseDpr * (0.72 + qualityFactor * 0.4)));
    setDpr(Number(nextDpr.toFixed(2)));
  }, [initialDpr, qualityFactor, reducedMotion, setDpr]);

  return null;
}

function CameraRig({
  cameraPreset,
  controlsRef,
  defaults,
  focusTarget,
  reducedMotion
}: {
  cameraPreset: SceneCameraPreset;
  controlsRef: MutableRefObject<any>;
  defaults?: ScenePayload["camera_defaults"];
  focusTarget: FocusTarget | null;
  reducedMotion: boolean;
}) {
  const { camera } = useThree();
  const isFocusPreset =
    cameraPreset === "focus" &&
    Number.isFinite(focusTarget?.lat) &&
    Number.isFinite(focusTarget?.lon);
  const isFreePreset = cameraPreset === "free";

  const targetVector = useMemo(() => {
    const lat = isFocusPreset
      ? Number(focusTarget?.lat)
      : Number(defaults?.target_lat ?? 0);
    const lon = isFocusPreset
      ? Number(focusTarget?.lon)
      : Number(defaults?.target_lon ?? 0);
    return latLonToVector(lat, lon, GLOBE_RADIUS, 0.02).applyEuler(SCENE_ROTATION);
  }, [
    defaults?.target_lat,
    defaults?.target_lon,
    focusTarget?.lat,
    focusTarget?.lon,
    isFocusPreset
  ]);

  const cameraVector = useMemo(() => {
    const baseDistance = Math.max(2.6, Number(defaults?.distance ?? 3.35));
    const distance = isFocusPreset
      ? Math.max(2.45, baseDistance - 0.35)
      : Math.max(2.8, baseDistance);
    return targetVector.clone().normalize().multiplyScalar(distance);
  }, [defaults?.distance, isFocusPreset, targetVector]);

  useEffect(() => {
    if (!isFreePreset) return;
    const controls = controlsRef.current;
    if (controls?.target) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }, [controlsRef, isFreePreset]);

  useEffect(() => {
    if (!reducedMotion || isFreePreset) return;
    camera.position.copy(cameraVector);
    const controls = controlsRef.current;
    if (controls?.target) {
      controls.target.copy(targetVector.clone().multiplyScalar(0.45));
      controls.update();
      return;
    }
    camera.lookAt(targetVector);
  }, [camera, cameraVector, controlsRef, isFreePreset, reducedMotion, targetVector]);

  useFrame(() => {
    if (reducedMotion || isFreePreset) return;
    camera.position.lerp(cameraVector, 0.075);
    const controls = controlsRef.current;
    if (controls?.target) {
      const target = targetVector.clone().multiplyScalar(0.45);
      controls.target.lerp(target, 0.12);
      controls.update();
    } else {
      camera.lookAt(targetVector);
    }
  });

  return null;
}

function GlobeShell({
  contextTexture,
  qualityFactor,
  reducedMotion
}: {
  contextTexture: THREE.Texture | null;
  qualityFactor: number;
  reducedMotion: boolean;
}) {
  const atmosphereRef = useRef<Mesh | null>(null);
  const edgeGeometry = useMemo(
    () => new THREE.SphereGeometry(GLOBE_RADIUS, reducedMotion ? 16 : 24, reducedMotion ? 16 : 24),
    [reducedMotion]
  );
  const shellSegments = reducedMotion ? 42 : 64;
  const atmosphereOpacity = reducedMotion ? 0.05 : 0.05 + qualityFactor * 0.05;

  useFrame((state) => {
    if (!reducedMotion && atmosphereRef.current) {
      atmosphereRef.current.rotation.y = state.clock.elapsedTime * 0.03;
    }
  });

  return (
    <group>
      <mesh>
        <sphereGeometry args={[GLOBE_RADIUS, shellSegments, shellSegments]} />
        <meshStandardMaterial
          color="#05111a"
          emissive="#0e513c"
          emissiveIntensity={0.45 + qualityFactor * 0.25}
          roughness={0.82}
          metalness={0.12}
          transparent
          opacity={0.9}
        />
      </mesh>
      {contextTexture ? (
        <mesh scale={1.002}>
          <sphereGeometry args={[GLOBE_RADIUS, shellSegments, shellSegments]} />
          <meshBasicMaterial
            map={contextTexture}
            transparent
            opacity={0.92}
          />
        </mesh>
      ) : null}
      <mesh ref={atmosphereRef} scale={1.07}>
        <sphereGeometry args={[GLOBE_RADIUS, shellSegments, shellSegments]} />
        <meshBasicMaterial
          color="#48f1a6"
          transparent
          opacity={atmosphereOpacity}
          side={THREE.BackSide}
        />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[edgeGeometry]} />
        <lineBasicMaterial color="#48f1a6" transparent opacity={reducedMotion ? 0.08 : 0.12} />
      </lineSegments>
    </group>
  );
}

function TrackerTrail({
  active,
  feature
}: {
  active: boolean;
  feature: SceneFeature;
}) {
  const coordinates = Array.isArray(feature.geometry.coordinates)
    ? (feature.geometry.coordinates as number[][])
    : [];
  const points = useMemo(
    () =>
      coordinates
        .filter((coord) => Array.isArray(coord) && coord.length >= 2)
        .map((coord) => latLonToVector(coord[1], coord[0], GLOBE_RADIUS, 0.03)),
    [coordinates]
  );

  if (points.length < 2) return null;

  return (
    <Line
      points={points}
      color={active ? "#9cffdb" : "#48f1a6"}
      lineWidth={active ? 2.2 : 1.2}
      transparent
      opacity={active ? 0.95 : 0.5}
    />
  );
}

function HotspotPulse({
  feature,
  onSelect,
  reducedMotion,
  selected
}: {
  feature: SceneFeature;
  onSelect: (id: string) => void;
  reducedMotion: boolean;
  selected: boolean;
}) {
  const outerRef = useRef<Mesh | null>(null);
  const innerRef = useRef<Mesh | null>(null);
  const coords = Array.isArray(feature.geometry.coordinates)
    ? (feature.geometry.coordinates as number[])
    : [];
  const properties = asRecord(feature.properties);
  const presentation = asRecord(properties?.presentation);
  const accent = pulseAccent(feature);
  const intensity = Math.max(
    0.3,
    Math.min(1, getNumericValue(presentation?.pulse_intensity) ?? 0.55)
  );
  const position = useMemo(() => {
    if (coords.length < 2) {
      return new THREE.Vector3(0, 0, 0);
    }
    return latLonToVector(coords[1], coords[0], GLOBE_RADIUS, 0.018);
  }, [coords]);
  const pulseOffset = useMemo(() => feature.id.length * 0.11, [feature.id]);

  useEffect(() => {
    if (!reducedMotion) return;
    outerRef.current?.scale.set(1.55 + intensity * 0.35, 0.8, 1.55 + intensity * 0.35);
    innerRef.current?.scale.set(1.15 + intensity * 0.28, 0.72, 1.15 + intensity * 0.28);
  }, [intensity, reducedMotion]);

  useFrame((state) => {
    if (reducedMotion) return;
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 1.45 + pulseOffset) * 0.12;
    const selectedBoost = selected ? 0.18 : 0;
    outerRef.current?.scale.set(
      (1.45 + intensity * 0.34 + selectedBoost) * pulse,
      0.78,
      (1.45 + intensity * 0.34 + selectedBoost) * pulse
    );
    innerRef.current?.scale.set(
      (1.08 + intensity * 0.24 + selectedBoost) * pulse,
      0.72,
      (1.08 + intensity * 0.24 + selectedBoost) * pulse
    );
  });

  return (
    <group
      position={position}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(feature.id);
      }}
    >
      <mesh ref={outerRef}>
        <sphereGeometry args={[0.1 + intensity * 0.04, 18, 18]} />
        <meshBasicMaterial color={accent} transparent opacity={selected ? 0.22 : 0.13} depthWrite={false} />
      </mesh>
      <mesh ref={innerRef}>
        <sphereGeometry args={[0.065 + intensity * 0.03, 18, 18]} />
        <meshBasicMaterial color={accent} transparent opacity={selected ? 0.2 : 0.12} depthWrite={false} />
      </mesh>
    </group>
  );
}

function LivePoint({
  accentColor,
  feature,
  intensity,
  intelLens,
  onSelect,
  reducedMotion,
  sceneId,
  selected
}: {
  accentColor: string;
  feature: SceneFeature;
  intensity: number;
  intelLens: IntelSceneLens;
  onSelect: (id: string) => void;
  reducedMotion: boolean;
  sceneId: SceneId;
  selected: boolean;
}) {
  const markerRef = useRef<Mesh | null>(null);
  const haloRef = useRef<Mesh | null>(null);
  const coords = Array.isArray(feature.geometry.coordinates)
    ? (feature.geometry.coordinates as number[])
    : [];
  const tooltipDetails = useMemo(
    () => getTooltipDetailLines(feature, sceneId, intelLens),
    [feature, intelLens, sceneId]
  );
  const position = useMemo(() => {
    if (coords.length < 2) {
      return new THREE.Vector3(0, 0, 0);
    }
    return latLonToVector(coords[1], coords[0], GLOBE_RADIUS, 0.045);
  }, [coords]);
  const kind = String(asRecord(feature.properties)?.kind || "").toLowerCase();
  const isFlight = kind === "flight";
  const headingDeg = getNumericValue(asRecord(feature.properties)?.heading_deg);
  const orientation = useMemo(() => {
    if (!isFlight || coords.length < 2) {
      return new THREE.Quaternion();
    }
    const up = latLonToVector(coords[1], coords[0], 1, 0).normalize();
    const east = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), up);
    if (east.lengthSq() < 1e-6) {
      east.set(1, 0, 0);
    } else {
      east.normalize();
    }
    const north = new THREE.Vector3().crossVectors(up, east).normalize();
    const heading = ((headingDeg ?? 0) * Math.PI) / 180;
    const forward = north.multiplyScalar(Math.cos(heading)).add(east.multiplyScalar(Math.sin(heading))).normalize();
    return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), forward);
  }, [coords, headingDeg, isFlight]);
  const pulseOffset = useMemo(() => feature.id.length * 0.17, [feature.id]);

  useEffect(() => {
    if (!reducedMotion) return;
    markerRef.current?.scale.setScalar(selected ? 1.08 + intensity * 0.28 : 0.92 + intensity * 0.18);
    haloRef.current?.scale.setScalar(selected ? 1.28 + intensity * 0.24 : 1.02 + intensity * 0.18);
  }, [intensity, reducedMotion, selected]);

  useFrame((state) => {
    if (reducedMotion) return;
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.8 + pulseOffset) * 0.14;
    if (markerRef.current) {
      const baseScale = selected ? 1.04 + intensity * 0.32 : 0.88 + intensity * 0.24;
      markerRef.current.scale.setScalar(pulse * baseScale);
    }
    if (haloRef.current) {
      haloRef.current.scale.setScalar(selected ? 1.18 + intensity * 0.42 : 0.96 + intensity * 0.3);
    }
  });

  return (
    <group
      position={position}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(feature.id);
      }}
    >
      <mesh ref={haloRef}>
        <sphereGeometry args={[selected ? 0.05 + intensity * 0.02 : 0.034 + intensity * 0.014, 18, 18]} />
        <meshBasicMaterial color={accentColor} transparent opacity={selected ? 0.28 : 0.15} />
      </mesh>
      {isFlight ? (
        <mesh ref={markerRef} quaternion={orientation}>
          <coneGeometry args={[0.011 + intensity * 0.005, 0.032 + intensity * 0.01, 8]} />
          <meshStandardMaterial
            color={accentColor}
            emissive={accentColor}
            emissiveIntensity={selected ? 1.8 : 1.25}
          />
        </mesh>
      ) : (
        <mesh ref={markerRef}>
          <sphereGeometry args={[selected ? 0.025 + intensity * 0.012 : 0.02 + intensity * 0.008, 18, 18]} />
          <meshStandardMaterial
            color={accentColor}
            emissive={accentColor}
            emissiveIntensity={selected ? 1.7 : 1.2}
          />
        </mesh>
      )}
      {selected ? (
        <Html distanceFactor={14}>
          <div className="globe-tooltip">
            <p className="globe-tooltip-title">
              {getFeatureLabel(feature)}
            </p>
            <p className="globe-tooltip-copy">
              {getFeatureTooltipCopy(
                feature,
                sceneId,
                intelLens
              )}
            </p>
            {tooltipDetails.map((detail) => (
              <p key={detail} className="globe-tooltip-copy globe-tooltip-copy--detail">
                {detail}
              </p>
            ))}
          </div>
        </Html>
      ) : null}
    </group>
  );
}

function EvidencePeak({
  accentColor,
  feature,
  onSelect,
  peakScale,
  selected
}: {
  accentColor: string;
  feature: SceneFeature;
  onSelect: (id: string) => void;
  peakScale: number;
  selected: boolean;
}) {
  const coords = Array.isArray(feature.geometry.coordinates)
    ? (feature.geometry.coordinates as number[])
    : [];
  const normal = useMemo(() => {
    if (coords.length < 2) return new THREE.Vector3(0, 1, 0);
    return latLonToVector(coords[1], coords[0], GLOBE_RADIUS, 0).normalize();
  }, [coords]);
  const height = 0.055 + peakScale * 0.16 + (selected ? 0.035 : 0);
  const position = useMemo(() => {
    if (coords.length < 2) return new THREE.Vector3(0, 0, 0);
    return latLonToVector(coords[1], coords[0], GLOBE_RADIUS, 0.052 + height / 2);
  }, [coords, height]);
  const quaternion = useMemo(
    () => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal),
    [normal]
  );

  if (coords.length < 2) return null;

  return (
    <mesh
      position={position}
      quaternion={quaternion}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(feature.id);
      }}
    >
      <coneGeometry args={[0.011 + peakScale * 0.018, height, 8, 1]} />
      <meshBasicMaterial
        color={accentColor}
        transparent
        opacity={selected ? 0.72 : 0.42}
        depthWrite={false}
      />
    </mesh>
  );
}

function GlobeScene({
  cameraPreset,
  contextTexture,
  intelLens,
  onQualityChange,
  onSelect,
  qualityFactor,
  reducedMotion,
  scene,
  sceneId,
  selectedFocus,
  selectedId,
  showIntelHotspots,
  showIntelRegions,
  showTrackerPoints,
  showTrackerTrails,
}: {
  cameraPreset: SceneCameraPreset;
  contextTexture: THREE.Texture | null;
  intelLens: IntelSceneLens;
  onQualityChange: (factor: number) => void;
  onSelect: (id: string) => void;
  qualityFactor: number;
  reducedMotion: boolean;
  scene: ScenePayload;
  sceneId: SceneId;
  selectedFocus: FocusTarget | null;
  selectedId: string | null;
  showIntelHotspots: boolean;
  showIntelRegions: boolean;
  showTrackerPoints: boolean;
  showTrackerTrails: boolean;
}) {
  const controlsRef = useRef<any>(null);
  const pointLayers = scene.layers.filter((layer) => layer.kind === "point");
  const pathLayers = scene.layers.filter((layer) => layer.kind === "path");
  const pulseLayers = scene.layers.filter((layer) => layer.kind === "pulse");
  const liveFeatures = pointLayers
    .flatMap((layer) => layer.features || [])
    .filter((feature) => (isIntelFeature(feature) ? showIntelRegions : showTrackerPoints));
  const pathFeatures = showTrackerTrails
    ? pathLayers.flatMap((layer) => layer.features || [])
    : [];
  const pulseFeatures = showIntelHotspots
    ? pulseLayers
        .flatMap((layer) => layer.features || [])
        .filter((feature) => pulseMatchesLens(feature, intelLens))
    : [];
  const peakFeatures = useMemo(() => {
    const values = liveFeatures
      .map((feature) => ({
        feature,
        rawValue: getFeaturePeakRawValue(feature, sceneId, intelLens)
      }))
      .filter((entry): entry is { feature: SceneFeature; rawValue: number } =>
        typeof entry.rawValue === "number" && Number.isFinite(entry.rawValue) && entry.rawValue > 0
      );
    const maxRawValue = Math.max(...values.map((entry) => entry.rawValue), 1);
    return values
      .map((entry) => ({
        feature: entry.feature,
        peakScale: Math.max(0.18, Math.min(1, entry.rawValue / maxRawValue))
      }))
      .sort((left, right) => right.peakScale - left.peakScale)
      .slice(0, reducedMotion ? 24 : 42);
  }, [intelLens, liveFeatures, reducedMotion, sceneId]);
  const activeQuality = reducedMotion ? 0.5 : qualityFactor;
  const starsCount = reducedMotion ? 450 : Math.round(1200 + activeQuality * 2200);
  const bloomIntensity = reducedMotion ? 0.25 : 0.35 + activeQuality * 0.55;
  const showHotspotOverlays =
    (sceneId === "intel" || sceneId === "overview") && showIntelHotspots;

  return (
    <Canvas
      camera={{ position: [0, 0, 4.2], fov: 42 }}
      dpr={reducedMotion ? 1 : [1, 1.6]}
      performance={{ min: 0.55, debounce: 300 }}
    >
      <AdaptiveDprController qualityFactor={activeQuality} reducedMotion={reducedMotion} />
      {!reducedMotion ? (
        <PerformanceMonitor
          bounds={(refreshrate) => (refreshrate > 100 ? [55, 100] : [40, 58])}
          onChange={({ factor }) => onQualityChange(Math.max(0.4, factor))}
          onFallback={() => onQualityChange(0.38)}
        />
      ) : null}
      <color attach="background" args={["#02060b"]} />
      <fog attach="fog" args={["#02060b", 4.2, 8]} />
      <ambientLight intensity={0.42} />
      <directionalLight
        position={[4, 3, 5]}
        intensity={0.85 + activeQuality * 0.55}
        color="#c8fff0"
      />
      <pointLight
        position={[-3, 2, -4]}
        intensity={reducedMotion ? 0.45 : 0.45 + activeQuality * 0.4}
        color="#48f1a6"
      />
      {!reducedMotion ? (
        <Stars
          radius={80}
          depth={40}
          count={starsCount}
          factor={3.2}
          saturation={0}
          fade
          speed={0.55}
        />
      ) : null}
      <CameraRig
        cameraPreset={cameraPreset}
        focusTarget={selectedFocus}
        defaults={scene.camera_defaults}
        controlsRef={controlsRef}
        reducedMotion={reducedMotion}
      />
      <group rotation={SCENE_ROTATION_VALUES}>
        <GlobeShell
          contextTexture={contextTexture}
          qualityFactor={activeQuality}
          reducedMotion={reducedMotion}
        />
        <group>
          {pathFeatures.map((feature) => {
            const trackerId = String(feature.properties?.tracker_id || "");
            return (
              <TrackerTrail
                key={feature.id}
                feature={feature}
                active={Boolean(selectedId && trackerId === selectedId)}
              />
            );
          })}
        </group>
        <group>
          {showHotspotOverlays
            ? pulseFeatures.map((feature) => (
                <HotspotPulse
                  key={feature.id}
                  feature={feature}
                  onSelect={onSelect}
                  reducedMotion={reducedMotion}
                  selected={selectedId === feature.id}
                />
              ))
            : null}
        </group>
        <group>
          {peakFeatures.map(({ feature, peakScale }) => (
            <EvidencePeak
              key={`peak-${feature.id}`}
              accentColor={getFeatureAccent(feature, sceneId, intelLens)}
              feature={feature}
              onSelect={onSelect}
              peakScale={peakScale}
              selected={feature.id === selectedId}
            />
          ))}
        </group>
        <group>
          {liveFeatures.map((feature) => (
            <LivePoint
              key={feature.id}
              accentColor={getFeatureAccent(feature, sceneId, intelLens)}
              feature={feature}
              intensity={getFeatureIntensity(feature, sceneId, intelLens)}
              intelLens={intelLens}
              selected={feature.id === selectedId}
              reducedMotion={reducedMotion}
              sceneId={sceneId}
              onSelect={onSelect}
            />
          ))}
        </group>
      </group>
      <OrbitControls
        ref={controlsRef}
        enablePan={false}
        enableDamping={!reducedMotion}
        dampingFactor={0.08}
        autoRotate={!reducedMotion && cameraPreset === "overview"}
        autoRotateSpeed={0.35}
        rotateSpeed={0.85}
        zoomSpeed={0.9}
        minDistance={2.35}
        maxDistance={6.5}
      />
      <EffectComposer multisampling={0}>
        <Bloom intensity={bloomIntensity} luminanceThreshold={0.16} mipmapBlur />
      </EffectComposer>
    </Canvas>
  );
}

export function GlobeOverlay() {
  const {
    activeScene,
    activeScenePath,
    clearIntelFilters,
    clearTrackerFilters,
    closeScene,
    isOpen,
    openScene,
    resetOverlayVisibility,
    sceneState,
    setCameraPreset,
    setIntelIndustry,
    setIntelLens,
    setOverlayVisibility,
    setTrackerCategory,
    setTrackerCountry,
    setTrackerMode,
    setTrackerOperator,
    toggleIntelCategory,
    toggleIntelSource
  } = useSceneController();
  const reducedMotion = useReducedMotionPreference();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fallbackScene, setFallbackScene] = useState<ScenePayload | null>(null);
  const [fallbackError, setFallbackError] = useState<string | null>(null);
  const [geography, setGeography] = useState<GlobeGeographyData | null>(null);
  const [geographyError, setGeographyError] = useState<string | null>(null);
  const [qualityFactor, setQualityFactor] = useState(reducedMotion ? 0.5 : 0.82);
  const [warningsOpen, setWarningsOpen] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [trackerOperatorDraft, setTrackerOperatorDraft] = useState(sceneState.trackerOperator);
  const sceneId = activeScene?.id || "overview";
  const hasTrackerFallback = activeScene?.fallbackStrategy === "trackerSnapshot";
  const { data, error, loading, refresh } = useApi<ScenePayload>(
    activeScenePath || "/api/osint/scene/overview?mode=combined",
    {
      enabled: isOpen && Boolean(activeScene),
      interval: isOpen ? (sceneId === "trackers" ? 30000 : sceneId === "overview" ? 60000 : 120000) : 0
    }
  );
  const { data: intelMeta, error: intelMetaError } = useApi<IntelMeta>("/api/intel/meta", {
    enabled: isOpen && (sceneId === "intel" || sceneId === "overview"),
    interval: isOpen && (sceneId === "intel" || sceneId === "overview") ? 600000 : 0
  });
  const {
    data: clientIndex,
    error: clientContextError,
    warnings: clientContextWarnings
  } = useApi<ClientIndex>("/api/clients", {
    enabled: isOpen && sceneId === "overview",
    interval: isOpen && sceneId === "overview" ? 60000 : 0
  });

  useEffect(() => {
    setQualityFactor(reducedMotion ? 0.5 : 0.82);
  }, [reducedMotion]);

  useEffect(() => {
    setTrackerOperatorDraft(sceneState.trackerOperator);
  }, [sceneState.trackerOperator]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeScene();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeScene, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      setFallbackScene(null);
      setFallbackError(null);
      setGeographyError(null);
      setSelectedId(null);
      return;
    }
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen]);

  useEffect(() => {
    setFallbackScene(null);
    setFallbackError(null);
    setSelectedId(null);
    setWarningsOpen(false);
    setFiltersOpen(false);
    setControlsOpen(false);
    setBrowseOpen(false);
  }, [activeScene?.id]);

  useEffect(() => {
    if (!isOpen || geography || geographyError) return;
    let mounted = true;
    loadGlobeGeography()
      .then((payload) => {
        if (!mounted) return;
        setGeography(payload);
        setGeographyError(null);
      })
      .catch((geographyErr) => {
        if (!mounted) return;
        setGeographyError(
          geographyErr instanceof Error ? geographyErr.message : "Globe geography unavailable."
        );
      });
    return () => {
      mounted = false;
    };
  }, [geography, geographyError, isOpen]);

  useEffect(() => {
    if (!isOpen || !error || !activeScene || data || !hasTrackerFallback) return;
    let mounted = true;
    buildFallbackTrackerScene(sceneState.trackerMode)
      .then((scene) => {
        if (mounted) {
          setFallbackScene(scene);
          setFallbackError(null);
        }
      })
      .catch((sceneErr) => {
        if (mounted) {
          setFallbackScene(null);
          setFallbackError(
            sceneErr instanceof Error ? sceneErr.message : "Fallback scene unavailable."
          );
        }
      });
    return () => {
      mounted = false;
    };
  }, [activeScene, data, error, hasTrackerFallback, isOpen, sceneState.trackerMode]);

  useEffect(() => {
    if (!data) return;
    setFallbackScene(null);
    setFallbackError(null);
  }, [data]);

  const scene = data || fallbackScene;
  const pointLayers = scene?.layers.filter((layer) => layer.kind === "point") || [];
  const pathLayers = scene?.layers.filter((layer) => layer.kind === "path") || [];
  const pulseLayers = scene?.layers.filter((layer) => layer.kind === "pulse") || [];
  const pointFeatures = pointLayers.flatMap((layer) => layer.features || []);
  const pathFeatures = pathLayers.flatMap((layer) => layer.features || []);
  const pulseFeatures = pulseLayers.flatMap((layer) => layer.features || []);
  const trackerPointFeatures = pointFeatures.filter((feature) => !isIntelFeature(feature));
  const intelPointFeatures = pointFeatures.filter((feature) => isIntelFeature(feature));
  const visibleTrackerPointFeatures = sceneState.showTrackerPoints ? trackerPointFeatures : [];
  const visibleIntelPointFeatures = sceneState.showIntelRegions ? intelPointFeatures : [];
  const visiblePointFeatures = [...visibleTrackerPointFeatures, ...visibleIntelPointFeatures];
  const visiblePathFeatures = sceneState.showTrackerTrails ? pathFeatures : [];
  const visiblePulseFeatures = sceneState.showIntelHotspots
    ? pulseFeatures.filter((feature) => pulseMatchesLens(feature, sceneState.intelLens))
    : [];
  const warnings = Array.from(
    new Set([
      ...(geographyError ? [`Geography overlay unavailable: ${geographyError}`] : []),
      ...(intelMetaError && (sceneId === "intel" || sceneId === "overview")
        ? [`Signal metadata unavailable: ${intelMetaError}`]
        : []),
      ...(clientContextError && sceneId === "overview"
        ? [`Client context unavailable: ${clientContextError}`]
        : []),
      ...(sceneId === "overview"
        ? clientContextWarnings.map((warning) => `Client context: ${warning}`)
        : []),
      ...(error ? [error] : []),
      ...(fallbackError ? [fallbackError] : []),
      ...((scene?.meta?.warnings || []) as string[])
    ])
  );
  const waitingOnFallback = Boolean(
    hasTrackerFallback && error && !data && !fallbackScene && !fallbackError
  );
  const sceneUnavailable =
    !scene && !loading && !waitingOnFallback && Boolean(error || fallbackError);
  const scenePending = isOpen && !scene && !sceneUnavailable;

  const visibleFocusTargets = useMemo(
    () => {
      const primaryTargets = (scene?.focus_targets || []).filter((target) => {
        if (target.domain === "intel") return sceneState.showIntelRegions;
        if (target.domain === "trackers") return sceneState.showTrackerPoints;
        return true;
      });
      const pulseTargets = visiblePulseFeatures.flatMap((feature): FocusTarget[] => {
        const coordinates = getFeatureCoordinates(feature);
        if (!coordinates) return [];
        const properties = asRecord(feature.properties);
        return [{
          id: feature.id,
          label: String(properties?.label || feature.id),
          domain: "intel",
          kind: String(properties?.channel || properties?.kind || "signal"),
          category: String(properties?.category || "signal"),
          lat: coordinates.lat,
          lon: coordinates.lon,
          confidence: null
        }];
      });
      return [...primaryTargets, ...pulseTargets];
    },
    [scene, sceneState.showIntelRegions, sceneState.showTrackerPoints, visiblePulseFeatures]
  );

  useEffect(() => {
    if (!visibleFocusTargets.length) {
      setSelectedId(null);
      return;
    }
    if (selectedId && !visibleFocusTargets.some((target) => target.id === selectedId)) {
      setSelectedId(null);
    }
  }, [selectedId, visibleFocusTargets]);

  const geographyTexture = useMemo(() => {
    if (!geography) return null;
    const canvas = buildGlobeContextCanvas(geography, reducedMotion ? 1024 : 2048);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    return texture;
  }, [geography, reducedMotion]);

  useEffect(() => {
    return () => {
      geographyTexture?.dispose();
    };
  }, [geographyTexture]);

  const selectedFocus = useMemo(
    () =>
      selectedId
        ? visibleFocusTargets.find((target) => target.id === selectedId) || null
        : null,
    [selectedId, visibleFocusTargets]
  );
  const selectedFeature = useMemo(
    () =>
      selectedId
        ? [...visiblePointFeatures, ...visiblePulseFeatures].find(
            (feature) => feature.id === selectedId
          ) || null
        : null,
    [selectedId, visiblePointFeatures, visiblePulseFeatures]
  );
  const selectedTrail = useMemo(
    () =>
      visiblePathFeatures.find(
        (feature) => String(asRecord(feature.properties)?.tracker_id || "") === String(selectedId || "")
      ) || null,
    [selectedId, visiblePathFeatures]
  );
  const intelHighRiskCount = useMemo(
    () =>
      visibleIntelPointFeatures.filter((feature) => {
        const score = getFeatureLensScore(feature, "combined");
        return score !== null && score >= 6;
      }).length,
    [visibleIntelPointFeatures]
  );

  const trackerCategoryEntries = useMemo(() => {
    const counts = new Map<string, number>();
    trackerPointFeatures.forEach((feature) => {
      const category = String(asRecord(feature.properties)?.category || "").trim();
      if (!category) return;
      counts.set(category, (counts.get(category) || 0) + 1);
    });
    if (sceneState.trackerCategory !== "all" && !counts.has(sceneState.trackerCategory)) {
      counts.set(sceneState.trackerCategory, 0);
    }
    return Array.from(counts.entries()).sort(
      (left, right) => right[1] - left[1] || left[0].localeCompare(right[0])
    );
  }, [sceneState.trackerCategory, trackerPointFeatures]);

  const trackerCountryOptions = useMemo(() => {
    const countries = new Set<string>();
    trackerPointFeatures.forEach((feature) => {
      const country = String(asRecord(feature.properties)?.country || "").trim();
      if (country) countries.add(country);
    });
    if (sceneState.trackerCountry.trim()) {
      countries.add(sceneState.trackerCountry.trim());
    }
    return Array.from(countries).sort((left, right) => left.localeCompare(right));
  }, [sceneState.trackerCountry, trackerPointFeatures]);

  const topTrackerOperators = useMemo(() => {
    const counts = new Map<string, number>();
    trackerPointFeatures.forEach((feature) => {
      const properties = asRecord(feature.properties);
      const operator = String(properties?.operator_name || properties?.operator || "").trim();
      if (!operator) return;
      counts.set(operator, (counts.get(operator) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .slice(0, 4);
  }, [trackerPointFeatures]);

  const selectedProvenanceRows = useMemo(() => {
    const rows: Array<{ label: string; value: string }> = [];
    if (!selectedFeature) return rows;

    const properties = asRecord(selectedFeature.properties);
    const provenance = asRecord(properties?.provenance);
    const addRow = (label: string, value: string) => {
      rows.push({ label, value: value && value !== "n/a" ? value : "n/a" });
    };

    addRow("Source", formatFeatureSource(selectedFeature));
    addRow("Layer", formatDisplayLabel(selectedFeature.layer));
    addRow("Display Scope", formatDisplayLabel(properties?.display_scope || properties?.scope_kind));
    addRow("Coverage", formatCoverage(asRecord(properties?.coverage)));
    addRow("Feature Warnings", formatStringList(selectedFeature.warnings));
    addRow("Display Note", formatOptionalText(provenance?.display_note || properties?.display_note));
    return rows;
  }, [selectedFeature]);

  const selectedDetailRows = useMemo(() => {
    const rows: Array<{ label: string; value: string }> = [];
    if (!selectedFeature) return rows;

    const properties = asRecord(selectedFeature.properties);
    const selectedIntelFeature = sceneId === "intel" || (sceneId === "overview" && isIntelFeature(selectedFeature));
    const coordinates = getFeatureCoordinates(selectedFeature);
    const addRow = (label: string, value: string) => {
      if (!value || value === "n/a") return;
      rows.push({ label, value });
    };

    addRow(
      "Coordinates",
      coordinates
        ? `${formatCoordinate(coordinates.lat, "lat")} • ${formatCoordinate(coordinates.lon, "lon")}`
        : "n/a"
    );
    addRow("Updated", formatTimestamp(selectedFeature.ts));
    addRow(
      "Freshness",
      formatAge(selectedFeature.freshness?.age_sec, selectedFeature.freshness?.state)
    );

    const signalChannel = String(properties?.channel || "").trim();
    if (signalChannel) {
      addRow("Channel", formatDisplayLabel(signalChannel));
      addRow("Signal Score", formatMetricValue(
        properties?.conflict_score ?? properties?.weather_score ?? properties?.risk_score,
        "/10"
      ));
      addRow("Supporting Articles", formatMetricValue(properties?.article_count));
      addRow("Context Tags", formatTopCountList(asRecord(properties?.event_counts)));
      addRow("Impacted Markets", formatTopCountList(asRecord(properties?.impact_counts)));
      addRow("Signals", formatStringList(properties?.signals));
      addRow("Impacts", formatStringList(properties?.impacts));
      addRow("Scope", formatDisplayLabel(properties?.display_scope));
    } else if (selectedIntelFeature) {
      const combined = asRecord(properties?.combined_risk);
      const weather = asRecord(properties?.weather);
      const conflict = asRecord(properties?.conflict);
      const news = asRecord(properties?.news);
      const emotion = asRecord(properties?.emotion);
      const combinedScore = getNumericValue(combined?.score);
      const weatherScore = getNumericValue(weather?.score);
      const conflictScore = getNumericValue(conflict?.score);

      addRow(
        "Combined Signal",
        combinedScore !== null
          ? `${Math.round(combinedScore)}/10 • ${formatDisplayLabel(combined?.level)}`
          : formatDisplayLabel(combined?.level)
      );
      addRow(
        "Weather",
        weatherScore !== null
          ? `${Math.round(weatherScore)}/10 • ${formatDisplayLabel(weather?.status || weather?.level)}`
          : formatDisplayLabel(weather?.status || weather?.level)
      );
      addRow(
        "Conflict",
        conflictScore !== null
          ? `${Math.round(conflictScore)}/10 • ${formatDisplayLabel(conflict?.status || conflict?.level)}`
          : formatDisplayLabel(conflict?.status || conflict?.level)
      );
      addRow("Headlines", `${Math.round(getNumericValue(news?.count) || 0)}`);
      addRow("Conflict Articles", `${Math.round(getNumericValue(conflict?.count) || 0)}`);
      addRow(
        "Dominant Emotion",
        formatDisplayLabel(emotion?.dominant || getDominantEmotion(selectedFeature))
      );
      addRow("Emotion Observations", `${Math.round(getNumericValue(emotion?.count) || 0)}`);
      addRow("Sentiment Avg", formatMetricValue(news?.sentiment_avg));
      addRow("Negative Share", formatRatioAsPercent(news?.negative_ratio));
      addRow("Context Tags", formatTopCountList(asRecord(news?.event_counts)));
      addRow("Impacted Markets", formatTopCountList(asRecord(news?.impact_counts)));
      addRow("Industries", formatStringList(properties?.industries));
      addRow("Top Sources", formatStringList(news?.top_sources));
      addRow("Scope", formatDisplayLabel(properties?.display_scope));
    } else {
      addRow(
        "Type",
        `${String(properties?.kind || "signal").toUpperCase()} • ${formatDisplayLabel(properties?.category)}`
      );
      addRow("ICAO24", formatDisplayLabel(properties?.icao24));
      addRow("Callsign", formatDisplayLabel(properties?.callsign));
      addRow("Flight", formatDisplayLabel(properties?.flight_number));
      addRow("Tail", formatDisplayLabel(properties?.tail_number));
      addRow("Operator", formatDisplayLabel(properties?.operator_name || properties?.operator));
      addRow("Operator Country", formatDisplayLabel(properties?.operator_country));
      addRow("Country", formatDisplayLabel(properties?.country));
      addRow("Speed", formatMetricValue(properties?.speed_kts, " kts"));
      addRow("Speed Volatility", formatMetricValue(properties?.speed_vol_kts, " kts"));
      addRow("Altitude", formatMetricValue(properties?.altitude_ft, " ft"));
      addRow("Heading", formatMetricValue(properties?.heading_deg, "°"));
      if (selectedTrail) {
        const trailProperties = asRecord(selectedTrail.properties);
        addRow("Trail Distance", formatMetricValue(trailProperties?.distance_km, " km"));
        addRow("Trail Duration", formatDuration(trailProperties?.duration_sec));
        if (typeof trailProperties?.route_hint === "string" && trailProperties.route_hint.trim()) {
          addRow("Route Hint", trailProperties.route_hint.trim());
        }
      }
    }

    return rows;
  }, [sceneId, selectedFeature, selectedTrail]);

  const selectedEmotionMix = useMemo(() => {
    if (!selectedFeature || !(sceneId === "intel" || (sceneId === "overview" && isIntelFeature(selectedFeature)))) {
      return [];
    }
    return getTopEntries(asRecord(asRecord(asRecord(selectedFeature.properties)?.emotion)?.counts), 5).map(
      ([emotion, count]) => ({
        emotion,
        count: Math.round(Number(count) || 0)
      })
    );
  }, [sceneId, selectedFeature]);

  const selectedContextMix = useMemo(() => {
    if (!selectedFeature || !(sceneId === "intel" || (sceneId === "overview" && isIntelFeature(selectedFeature)))) {
      return [];
    }
    return getTopEntries(asRecord(asRecord(asRecord(selectedFeature.properties)?.news)?.event_counts), 5).map(
      ([name, count]) => ({
        name,
        count: Math.round(Number(count) || 0)
      })
    );
  }, [sceneId, selectedFeature]);

  const selectedImpactMix = useMemo(() => {
    if (!selectedFeature || !(sceneId === "intel" || (sceneId === "overview" && isIntelFeature(selectedFeature)))) {
      return [];
    }
    return getTopEntries(asRecord(asRecord(asRecord(selectedFeature.properties)?.news)?.impact_counts), 5).map(
      ([name, count]) => ({
        name,
        count: Math.round(Number(count) || 0)
      })
    );
  }, [sceneId, selectedFeature]);

  const aggregateRows = useMemo(() => {
    if (sceneId === "trackers" || sceneId === "overview") {
      const kindCounts = new Map<string, number>();
      const categoryCounts = new Map<string, number>();
      const countryCounts = new Map<string, number>();
      const operatorCounts = new Map<string, number>();
      const speedSamples: number[] = [];

      visibleTrackerPointFeatures.forEach((feature) => {
        const properties = asRecord(feature.properties);
        const kind = String(properties?.kind || "").trim();
        const category = String(properties?.category || "").trim();
        const country = String(properties?.country || "").trim();
        const operator = String(properties?.operator_name || properties?.operator || "").trim();
        const speed = getNumericValue(properties?.speed_kts);
        if (kind) kindCounts.set(kind, (kindCounts.get(kind) || 0) + 1);
        if (category) categoryCounts.set(category, (categoryCounts.get(category) || 0) + 1);
        if (country) countryCounts.set(country, (countryCounts.get(country) || 0) + 1);
        if (operator) operatorCounts.set(operator, (operatorCounts.get(operator) || 0) + 1);
        if (speed !== null) speedSamples.push(speed);
      });

      const topValues = (entries: Map<string, number>) =>
        Array.from(entries.entries())
          .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
          .slice(0, 3)
          .map(([label, count]) => `${formatDisplayLabel(label)} (${count})`)
          .join(" • ") || "n/a";

      if (sceneId === "overview") {
        const overviewChannelCounts = new Map<string, number>();
        let overviewHeadlines = 0;
        visibleIntelPointFeatures.forEach((feature) => {
          const properties = asRecord(feature.properties);
          const news = asRecord(properties?.news);
          const dominantChannel = String(
            asRecord(properties?.presentation)?.dominant_channel || ""
          ).trim();
          overviewHeadlines += Math.round(getNumericValue(news?.count) || 0);
          if (dominantChannel) {
            overviewChannelCounts.set(
              dominantChannel,
              (overviewChannelCounts.get(dominantChannel) || 0) + 1
            );
          }
        });
        return [
          { label: "Live Trackers", value: `${visibleTrackerPointFeatures.length}` },
          { label: "Visible Regions", value: `${visibleIntelPointFeatures.length}` },
          { label: "Replay Trails", value: `${visiblePathFeatures.length}` },
          { label: "Centroid Highlights", value: `${visiblePulseFeatures.length}` },
          { label: "Elevated Signals", value: `${intelHighRiskCount}` },
          { label: "Top Tracker Categories", value: topValues(categoryCounts) },
          { label: "Top Operators", value: topValues(operatorCounts) },
          { label: "Regional Channels", value: topValues(overviewChannelCounts) },
          { label: "Headlines Across Nodes", value: `${overviewHeadlines}` },
        ];
      }

      return [
        { label: "Visible Flights", value: `${kindCounts.get("flight") || 0}` },
        { label: "Visible Vessels", value: `${kindCounts.get("ship") || 0}` },
        { label: "Replay Trails", value: `${visiblePathFeatures.length}` },
        { label: "Top Categories", value: topValues(categoryCounts) },
        { label: "Top Countries", value: topValues(countryCounts) },
        { label: "Top Operators", value: topValues(operatorCounts) },
        {
          label: "Mean Visible Speed",
          value: speedSamples.length
            ? `${Math.round(speedSamples.reduce((total, value) => total + value, 0) / speedSamples.length)} kts`
            : "n/a"
        }
      ];
    }

    const channelCounts = new Map<string, number>();
    const eventCounts = new Map<string, number>();
    const impactCounts = new Map<string, number>();
    const emotionCounts = new Map<string, number>();
    const sourceCounts = new Map<string, number>();
    let headlineCount = 0;

    visibleIntelPointFeatures.forEach((feature) => {
      const properties = asRecord(feature.properties);
      const news = asRecord(properties?.news);
      const dominantChannel = String(
        asRecord(properties?.presentation)?.dominant_channel || ""
      ).trim();
      headlineCount += Math.round(getNumericValue(news?.count) || 0);
      if (dominantChannel) {
        channelCounts.set(dominantChannel, (channelCounts.get(dominantChannel) || 0) + 1);
      }
      Object.entries(asRecord(news?.event_counts) || {}).forEach(([eventName, count]) => {
        eventCounts.set(
          eventName,
          (eventCounts.get(eventName) || 0) + Math.round(getNumericValue(count) || 0)
        );
      });
      Object.entries(asRecord(news?.impact_counts) || {}).forEach(([impactName, count]) => {
        impactCounts.set(
          impactName,
          (impactCounts.get(impactName) || 0) + Math.round(getNumericValue(count) || 0)
        );
      });
      Object.entries(asRecord(news?.emotion_counts) || {}).forEach(([emotion, count]) => {
        emotionCounts.set(
          emotion,
          (emotionCounts.get(emotion) || 0) + Math.round(getNumericValue(count) || 0)
        );
      });
      (Array.isArray(news?.top_sources) ? news.top_sources : []).forEach((source) => {
        if (typeof source !== "string" || !source.trim()) return;
        const key = source.trim();
        sourceCounts.set(key, (sourceCounts.get(key) || 0) + 1);
      });
    });

    const topValues = (entries: Map<string, number>) =>
      Array.from(entries.entries())
        .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
        .slice(0, 3)
        .map(([label, count]) => `${formatDisplayLabel(label)} (${count})`)
        .join(" • ") || "n/a";

    return [
      { label: "Visible Regions", value: `${visibleIntelPointFeatures.length}` },
      { label: "Visible Centroid Highlights", value: `${visiblePulseFeatures.length}` },
      { label: "Elevated Signals", value: `${intelHighRiskCount}` },
      { label: "Headlines Across Nodes", value: `${headlineCount}` },
      { label: "Dominant Channels", value: topValues(channelCounts) },
      { label: "Top Context Tags", value: topValues(eventCounts) },
      { label: "Impacted Markets", value: topValues(impactCounts) },
      { label: "Top Emotions", value: topValues(emotionCounts) },
      { label: "Most Referenced Sources", value: topValues(sourceCounts) },
      { label: "Industry Filter", value: formatDisplayLabel(sceneState.intelIndustry) }
    ];
  }, [
    intelHighRiskCount,
    visibleIntelPointFeatures,
    visiblePathFeatures.length,
    visiblePulseFeatures.length,
    sceneId,
    sceneState.intelIndustry,
    visibleTrackerPointFeatures,
  ]);

  const sceneLegendEntries = useMemo(() => {
    if (sceneId === "trackers") {
      const byCategory = new Map<string, { color: string; count: number; label: string }>();
      visibleTrackerPointFeatures.forEach((feature) => {
        const properties = asRecord(feature.properties);
        const rawCategory = String(properties?.category || properties?.kind || "signal").trim();
        const label = formatDisplayLabel(rawCategory);
        const existing = byCategory.get(label);
        byCategory.set(label, {
          label,
          color: getFeatureAccent(feature, sceneId, sceneState.intelLens),
          count: (existing?.count || 0) + 1
        });
      });
      return Array.from(byCategory.values())
        .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
        .slice(0, 6);
    }

    if (sceneState.intelLens === "emotion") {
      const emotionCounts = new Map<string, number>();
      visibleIntelPointFeatures.forEach((feature) => {
        Object.entries(asRecord(asRecord(feature.properties)?.news)?.emotion_counts || {}).forEach(
          ([emotion, count]) => {
            emotionCounts.set(
              emotion,
              (emotionCounts.get(emotion) || 0) + Math.round(getNumericValue(count) || 0)
            );
          }
        );
      });
      return Array.from(emotionCounts.entries())
        .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
        .slice(0, 6)
        .map(([emotion, count]) => ({
          label: `${formatDisplayLabel(emotion)} (${count})`,
          color: getEmotionAccent(emotion),
          count
        }));
    }

    const visibleLegendLayers = pointLayers.filter((layer) =>
      layer.id === "regional-intel" ? sceneState.showIntelRegions : sceneState.showTrackerPoints
    );
    const baseEntries = visibleLegendLayers
      .flatMap((layer) => layer.legend || [])
      .map((entry) => ({
        label: String(entry.label || entry.value || "Signal"),
        color: String(entry.color || "#48f1a6"),
        count: null
      }))
      .filter((entry, index, entries) =>
        entries.findIndex(
          (candidate) => candidate.label === entry.label && candidate.color === entry.color
        ) === index
      );
    if ((sceneId === "intel" || sceneId === "overview") && (sceneState.intelLens === "combined" || sceneState.intelLens === "conflict") && visiblePulseFeatures.length) {
      return [
        ...baseEntries,
        {
          label: `Conflict Pulse (${visiblePulseFeatures.length})`,
          color: "#ff5c6a",
          count: visiblePulseFeatures.length
        }
      ];
    }
    return baseEntries;
  }, [
    pointLayers,
    sceneId,
    sceneState.intelLens,
    sceneState.showIntelRegions,
    sceneState.showTrackerPoints,
    visibleIntelPointFeatures,
    visiblePulseFeatures.length,
    visibleTrackerPointFeatures,
  ]);

  const availableLenses = useMemo(() => {
    const raw = scene?.meta?.available_lenses || [];
    const wanted = new Set(
      raw
        .filter((value): value is string => typeof value === "string")
        .map((value) => value.toLowerCase())
    );
    if (!wanted.size) return INTEL_LENS_OPTIONS;
    return INTEL_LENS_OPTIONS.filter((option) => wanted.has(option.id));
  }, [scene?.meta?.available_lenses]);

  const geographySourceCopy = useMemo(() => {
    if (!geography) return "Base map loading";
    return `Base: ${geography.source.name} ${geography.source.dataset} / de facto admin context`;
  }, [geography]);

  const sceneHasIntel = sceneId === "intel" || sceneId === "overview";
  const sceneHasTrackers = sceneId === "trackers" || sceneId === "overview";
  const activeFilterCount =
    (sceneHasTrackers && sceneState.trackerCategory !== "all" ? 1 : 0) +
    (sceneHasTrackers && sceneState.trackerCountry.trim() ? 1 : 0) +
    (sceneHasTrackers && sceneState.trackerOperator.trim() ? 1 : 0) +
    (sceneHasIntel && sceneState.intelIndustry !== "all" ? 1 : 0) +
    (sceneHasIntel ? sceneState.intelCategories.length : 0) +
    (sceneHasIntel ? sceneState.intelSources.length : 0);
  const availableSceneItemCount =
    (sceneHasTrackers ? trackerPointFeatures.length + pathFeatures.length : 0) +
    (sceneHasIntel ? intelPointFeatures.length + pulseFeatures.length : 0);
  const hasHiddenAvailableData = Boolean(
    (sceneHasTrackers && trackerPointFeatures.length && !sceneState.showTrackerPoints) ||
    (sceneHasTrackers && pathFeatures.length && !sceneState.showTrackerTrails) ||
    (sceneHasIntel && intelPointFeatures.length && !sceneState.showIntelRegions) ||
    (sceneHasIntel && pulseFeatures.length && !sceneState.showIntelHotspots)
  );
  const noDataMatchesSavedFilters = availableSceneItemCount === 0 && activeFilterCount > 0;
  const commandSummary = noDataMatchesSavedFilters
    ? `No data matches ${activeFilterCount} saved ${activeFilterCount === 1 ? "filter" : "filters"}`
    : sceneId === "overview"
      ? `${trackerPointFeatures.length} trackers / ${intelPointFeatures.length} regions${hasHiddenAvailableData ? " available" : ""}`
      : sceneId === "intel"
        ? `${intelPointFeatures.length} regional signals${hasHiddenAvailableData ? " available" : ""}`
        : `${trackerPointFeatures.length} live trackers${hasHiddenAvailableData ? " available" : ""}`;
  const selectedFeatureIsIntel = Boolean(
    selectedFeature && (sceneId === "intel" || (sceneId === "overview" && isIntelFeature(selectedFeature)))
  );
  const densityItems = [
    ...(sceneHasTrackers
      ? [
          { label: "Trackers", value: visibleTrackerPointFeatures.length, accent: "#7dffd3" },
          { label: "Trails", value: visiblePathFeatures.length, accent: "#48f1a6" },
        ]
      : []),
    ...(sceneHasIntel
      ? [
          { label: "Regions", value: visibleIntelPointFeatures.length, accent: "#75d7ff" },
          { label: "Pulses", value: visiblePulseFeatures.length, accent: "#ff8b73" },
        ]
      : []),
  ];
  const clientRows = clientIndex?.clients || [];
  const clientContext = useMemo(() => {
    const accountCount = clientRows.reduce(
      (total, client) => total + (client.accounts_count || 0),
      0
    );
    const holdingsCount = clientRows.reduce(
      (total, client) => total + (client.holdings_count || 0),
      0
    );
    const topClients = [...clientRows]
      .sort(
        (left, right) =>
          (right.accounts_count || 0) - (left.accounts_count || 0) ||
          left.name.localeCompare(right.name)
      )
      .slice(0, 3);
    return {
      accountCount,
      clientCount: clientRows.length,
      holdingsCount,
      topClients,
    };
  }, [clientRows]);

  if (!isOpen || !activeScene) return null;

  return (
    <div
      className="globe-overlay"
      data-testid="globe-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={scene?.title || activeScene.label}
    >
      <div className="globe-overlay__backdrop" />
      <div className="globe-overlay__stage">
        {scene ? (
          <GlobeScene
            cameraPreset={sceneState.cameraPreset}
            contextTexture={geographyTexture}
            intelLens={sceneState.intelLens}
            scene={scene}
            sceneId={sceneId}
            selectedFocus={selectedFocus}
            selectedId={selectedId}
            reducedMotion={reducedMotion}
            qualityFactor={qualityFactor}
            onQualityChange={setQualityFactor}
            onSelect={(id) => {
              setSelectedId(id);
              setOverlayVisibility("detailsVisible", true);
            }}
            showIntelHotspots={sceneState.showIntelHotspots}
            showIntelRegions={sceneState.showIntelRegions}
            showTrackerPoints={sceneState.showTrackerPoints}
            showTrackerTrails={sceneState.showTrackerTrails}
          />
        ) : scenePending ? (
          <div className="globe-overlay__loading">
            <Orbit size={26} className="animate-spin text-emerald-300" />
            <p>Loading world view...</p>
            <p className="globe-overlay__status-copy">
              {waitingOnFallback
                ? "Refreshing from the live tracker snapshot."
                : "Requesting the current scene from the API."}
            </p>
          </div>
        ) : sceneUnavailable ? (
          <div className="globe-overlay__loading">
            <AlertTriangle size={26} className="text-amber-300" />
            <p>Scene unavailable.</p>
            <p className="globe-overlay__status-copy">
              {error || fallbackError || (
                hasTrackerFallback
                  ? "The world view could not load from the primary scene route or the tracker snapshot fallback."
                  : "The world view could not load from the primary regional scene route."
              )}
            </p>
            <div className="globe-overlay__actions">
              <button type="button" onClick={refresh} className="globe-action-button">
                Retry Scene
              </button>
              <button type="button" onClick={closeScene} className="globe-action-button">
                Close World
              </button>
            </div>
          </div>
        ) : (
          <div className="globe-overlay__loading">
            <Orbit size={26} className="animate-spin text-emerald-300" />
            <p>Loading world view...</p>
          </div>
        )}
      </div>

      <div className="globe-hud globe-hud--left max-h-screen overflow-y-auto">
        <div className="globe-panel globe-panel--compact">
          <div className="globe-panel__header">
            <div>
              <p className="tag text-[11px] uppercase tracking-[0.22em] text-emerald-300/90">
                World
              </p>
              <h2 className="globe-panel__title">
                {scene?.title || activeScene.label}
              </h2>
            </div>
            <button
              type="button"
              onClick={closeScene}
              className="globe-icon-button"
              aria-label="Close world view"
            >
              <X size={16} />
            </button>
          </div>
          <p className="globe-panel__label">Scene View</p>
          <div className="globe-toggle-group">
            {[
              { id: "overview" as SceneId, label: "World" },
              { id: "trackers" as SceneId, label: "Trackers" },
              { id: "intel" as SceneId, label: "Signals" },
            ].map((option) => (
              <button
                key={option.id}
                type="button"
                data-testid={`globe-scene-${option.id}`}
                aria-pressed={option.id === sceneId}
                onClick={() => {
                  openScene(option.id);
                  setCameraPreset("free");
                  setSelectedId(null);
                }}
                className={
                  option.id === sceneId
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="globe-command-summary">
            <span className="globe-badge">
              <RadioTower size={12} />
              {commandSummary}
            </span>
            <span className="globe-panel__copy globe-panel__copy--subtle">
              Select an object on the globe to inspect it.
            </span>
          </div>
          <div className="globe-command-actions">
            {hasHiddenAvailableData ? (
              <button
                type="button"
                data-testid="globe-show-available-layers"
                className="globe-action-button globe-action-button--active"
                onClick={() => resetOverlayVisibility()}
              >
                <Eye size={14} />
                Show available layers
              </button>
            ) : null}
            {noDataMatchesSavedFilters ? (
              <button
                type="button"
                data-testid="globe-clear-saved-filters"
                className="globe-action-button globe-action-button--active"
                onClick={() => {
                  if (sceneHasTrackers) clearTrackerFilters();
                  if (sceneHasIntel) clearIntelFilters();
                }}
              >
                <FilterX size={14} />
                Clear saved filters
              </button>
            ) : null}
            <button
              type="button"
              data-testid="globe-controls-toggle"
              className={controlsOpen ? "globe-action-button globe-action-button--active" : "globe-action-button"}
              aria-expanded={controlsOpen}
              aria-controls="globe-controls-panel"
              onClick={() => setControlsOpen((current) => !current)}
            >
              <SlidersHorizontal size={14} />
              {controlsOpen ? "Hide controls" : "Layers and view"}
              {activeFilterCount ? <span>{activeFilterCount}</span> : null}
            </button>
            <button
              type="button"
              data-testid="globe-browse-toggle"
              className={browseOpen ? "globe-action-button globe-action-button--active" : "globe-action-button"}
              aria-expanded={browseOpen}
              aria-controls="globe-browse-panel"
              onClick={() => {
                const next = !browseOpen;
                setBrowseOpen(next);
                if (next) {
                  setOverlayVisibility("detailsVisible", true);
                }
              }}
            >
              <List size={14} />
              Browse items
            </button>
          </div>
        </div>

        {controlsOpen ? (
          <div id="globe-controls-panel" className="globe-controls-stack">
        <div className="globe-panel globe-panel--compact">
          <div className="globe-panel__header">
            <div>
              <p className="globe-panel__label">Layers</p>
            </div>
            <button
              type="button"
              onClick={() => resetOverlayVisibility()}
              className="globe-action-button globe-action-button--inline"
            >
              Reset Layer View
            </button>
          </div>
          <div className="globe-toggle-group">
            {sceneHasTrackers ? (
              <button
                type="button"
                data-testid="globe-layer-trackers"
                aria-pressed={sceneState.showTrackerPoints}
                onClick={() => setOverlayVisibility("showTrackerPoints", !sceneState.showTrackerPoints)}
                className={
                  sceneState.showTrackerPoints
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                Trackers ({trackerPointFeatures.length})
              </button>
            ) : null}
            {sceneHasTrackers ? (
              <button
                type="button"
                data-testid="globe-layer-trails"
                aria-pressed={sceneState.showTrackerTrails}
                onClick={() => setOverlayVisibility("showTrackerTrails", !sceneState.showTrackerTrails)}
                className={
                  sceneState.showTrackerTrails
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                Trails ({pathFeatures.length})
              </button>
            ) : null}
            {sceneHasIntel ? (
              <button
                type="button"
                data-testid="globe-layer-regions"
                aria-pressed={sceneState.showIntelRegions}
                onClick={() => setOverlayVisibility("showIntelRegions", !sceneState.showIntelRegions)}
                className={
                  sceneState.showIntelRegions
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                Regional Signals ({intelPointFeatures.length})
              </button>
            ) : null}
            {sceneHasIntel ? (
              <button
                type="button"
                data-testid="globe-layer-hotspots"
                aria-pressed={sceneState.showIntelHotspots}
                onClick={() => setOverlayVisibility("showIntelHotspots", !sceneState.showIntelHotspots)}
                className={
                  sceneState.showIntelHotspots
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                {sceneState.intelLens === "combined" ? "Signal" : formatDisplayLabel(sceneState.intelLens)} Highlights ({visiblePulseFeatures.length})
              </button>
            ) : null}
          </div>
          {sceneHasTrackers ? (
            <>
              <p className="globe-panel__label">Tracker Scope</p>
              <div className="globe-toggle-group">
                {TRACKER_MODE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    data-testid={`globe-mode-${option.id}`}
                    aria-pressed={option.id === sceneState.trackerMode}
                    onClick={() => {
                      setTrackerMode(option.id);
                      setCameraPreset("free");
                      setSelectedId(null);
                    }}
                    className={
                      option.id === sceneState.trackerMode
                        ? "globe-toggle globe-toggle--active"
                        : "globe-toggle"
                    }
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          {sceneHasIntel ? (
            <>
              <p className="globe-panel__label">Signal Lens</p>
              <div className="globe-toggle-group">
                {availableLenses.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    data-testid={`globe-lens-${option.id}`}
                    aria-pressed={option.id === sceneState.intelLens}
                    onClick={() => {
                      setIntelLens(option.id);
                      setCameraPreset("free");
                    }}
                    className={
                      option.id === sceneState.intelLens
                        ? "globe-toggle globe-toggle--active"
                        : "globe-toggle"
                    }
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          {densityItems.length ? (
            <GlobeDataDensity
              title="Visible data"
              items={densityItems}
            />
          ) : null}
          <p className="globe-panel__label">Camera Preset</p>
          <div className="globe-toggle-group">
            {CAMERA_PRESET_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                data-testid={`globe-preset-${option.id}`}
                aria-pressed={option.id === sceneState.cameraPreset}
                onClick={() => setCameraPreset(option.id)}
                className={
                  option.id === sceneState.cameraPreset
                    ? "globe-toggle globe-toggle--active"
                    : "globe-toggle"
                }
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="globe-panel globe-panel--compact">
          <div className="globe-panel__header">
            <div>
              <p className="globe-panel__label">Filters</p>
              <p className="globe-panel__copy globe-panel__copy--subtle">
                {activeFilterCount
                  ? `${activeFilterCount} active ${activeFilterCount === 1 ? "filter" : "filters"}`
                  : "No extra filters"}
              </p>
            </div>
            <button
              type="button"
              className={filtersOpen ? "globe-toggle globe-toggle--active" : "globe-toggle"}
              aria-expanded={filtersOpen}
              aria-controls="globe-filter-content"
              onClick={() => setFiltersOpen((current) => !current)}
            >
              {filtersOpen ? "Hide Filters" : "Show Filters"}
            </button>
          </div>
          {filtersOpen && sceneHasIntel ? (
            <>
              <label className="globe-field">
                <span className="globe-panel__label">Industry</span>
                <select
                  value={sceneState.intelIndustry}
                  onChange={(event) => {
                    setIntelIndustry(event.target.value);
                    setCameraPreset("free");
                  }}
                  className="globe-field__control"
                >
                  {["all", ...(intelMeta?.industries || [])]
                    .filter((value, index, array) => array.indexOf(value) === index)
                    .map((option) => (
                      <option key={option} value={option}>
                        {formatDisplayLabel(option)}
                      </option>
                    ))}
                </select>
              </label>
              <p className="globe-panel__label">Contexts / Channels</p>
              <div className="globe-toggle-group">
                {(intelMeta?.categories || []).map((category) => (
                  <button
                    key={category}
                    type="button"
                    aria-pressed={sceneState.intelCategories.includes(category)}
                    onClick={() => {
                      toggleIntelCategory(category);
                      setCameraPreset("free");
                    }}
                    className={
                      sceneState.intelCategories.includes(category)
                        ? "globe-toggle globe-toggle--active"
                        : "globe-toggle"
                    }
                  >
                    {formatDisplayLabel(category)}
                  </button>
                ))}
              </div>
              <p className="globe-panel__label">Sources</p>
              <div className="globe-toggle-group">
                {(intelMeta?.sources || []).map((source) => (
                  <button
                    key={source}
                    type="button"
                    aria-pressed={sceneState.intelSources.includes(source)}
                    onClick={() => {
                      toggleIntelSource(source);
                      setCameraPreset("free");
                    }}
                    className={
                      sceneState.intelSources.includes(source)
                        ? "globe-toggle globe-toggle--active"
                        : "globe-toggle"
                    }
                  >
                    {source}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          {filtersOpen && sceneHasTrackers ? (
            <>
              <p className="globe-panel__label">Category</p>
              <div className="globe-toggle-group">
                <button
                  type="button"
                  aria-pressed={sceneState.trackerCategory === "all"}
                  onClick={() => {
                    setTrackerCategory("all");
                    setCameraPreset("free");
                  }}
                  className={
                    sceneState.trackerCategory === "all"
                      ? "globe-toggle globe-toggle--active"
                      : "globe-toggle"
                  }
                >
                  All Categories
                </button>
                {trackerCategoryEntries.map(([category, count]) => (
                  <button
                    key={category}
                    type="button"
                    aria-pressed={sceneState.trackerCategory === category}
                    onClick={() => {
                      setTrackerCategory(category);
                      setCameraPreset("free");
                    }}
                    className={
                      sceneState.trackerCategory === category
                        ? "globe-toggle globe-toggle--active"
                        : "globe-toggle"
                    }
                  >
                    {formatDisplayLabel(category)} ({count})
                  </button>
                ))}
              </div>
              <div className="globe-form-grid">
                <label className="globe-field">
                  <span className="globe-panel__label">Country</span>
                  <select
                    value={sceneState.trackerCountry || "__all__"}
                    onChange={(event) => {
                      setTrackerCountry(event.target.value === "__all__" ? "" : event.target.value);
                      setCameraPreset("free");
                    }}
                    className="globe-field__control"
                  >
                    <option value="__all__">All Countries</option>
                    {trackerCountryOptions.map((country) => (
                      <option key={country} value={country}>
                        {country}
                      </option>
                    ))}
                  </select>
                </label>
                <form
                  className="globe-field globe-field--wide"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setTrackerOperator(trackerOperatorDraft.trim());
                    setCameraPreset("free");
                  }}
                >
                  <span className="globe-panel__label">Operator</span>
                  <div className="globe-field__row">
                    <input
                      value={trackerOperatorDraft}
                      onChange={(event) => setTrackerOperatorDraft(event.target.value)}
                      placeholder="AAL, Maersk, Evergreen..."
                      className="globe-field__control"
                    />
                    <button
                      type="submit"
                      className="globe-action-button globe-action-button--inline"
                    >
                      Apply
                    </button>
                  </div>
                </form>
              </div>
              {topTrackerOperators.length ? (
                <p className="globe-panel__copy globe-panel__copy--subtle">
                  Top operators:{" "}
                  {topTrackerOperators.map(([label, count]) => `${label} (${count})`).join(" • ")}
                </p>
              ) : null}
            </>
          ) : null}
          {filtersOpen ? (
            <div id="globe-filter-content" className="globe-overlay__actions">
              {sceneHasTrackers ? (
                <button
                  type="button"
                  onClick={() => {
                    clearTrackerFilters();
                    setTrackerOperatorDraft("");
                    setCameraPreset("free");
                  }}
                  className="globe-action-button"
                >
                  Clear Tracker Filters
                </button>
              ) : null}
              {sceneHasIntel ? (
                <button
                  type="button"
                  onClick={() => {
                    clearIntelFilters();
                    setCameraPreset("free");
                  }}
                  className="globe-action-button"
                >
                  Clear Signal Filters
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="globe-panel globe-panel--compact">
          <p className="globe-panel__label">Scene Status</p>
          <p className="globe-panel__metric">
            {loading && !scene
              ? "Loading"
              : sceneUnavailable
                ? "Unavailable"
                : formatTimestamp(scene?.meta?.timestamp)}
          </p>
          <p className="globe-panel__copy globe-panel__copy--subtle">{geographySourceCopy}</p>
          {sceneUnavailable || (error && fallbackScene) || reducedMotion ? (
            <p className="globe-panel__copy">
              {sceneUnavailable
                ? "Scene unavailable."
                : error && fallbackScene
                  ? "Snapshot fallback active."
                  : "Reduced motion active."}
            </p>
          ) : null}
          {warnings.length ? (
            <div className="globe-warning-list">
              {warnings.slice(0, warningsOpen ? warnings.length : 3).map((warning) => (
                <p key={warning} className="globe-warning">
                  <AlertTriangle size={12} />
                  {warning}
                </p>
              ))}
              {warnings.length > 3 ? (
                <button
                  type="button"
                  className="globe-warning-toggle"
                  aria-expanded={warningsOpen}
                  onClick={() => setWarningsOpen((current) => !current)}
                >
                  {warningsOpen ? "Show fewer warnings" : `Show ${warnings.length - 3} more warnings`}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
          </div>
        ) : null}
      </div>

      <div
        className={
          sceneState.detailsVisible
            ? "globe-inspector globe-inspector--open"
            : "globe-inspector"
        }
        data-testid="globe-bottom-inspector"
      >
        <div className="globe-panel globe-panel--compact globe-inspector__handle">
          <div className="globe-panel__header globe-inspector__handle-row">
            <div>
              <p className="globe-panel__label">Context</p>
              <p className="globe-panel__metric">
                {selectedFocus?.label || "Select an object to inspect it"}
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                setOverlayVisibility("detailsVisible", !sceneState.detailsVisible)
              }
              className="globe-icon-button"
              aria-label={sceneState.detailsVisible ? "Collapse context panel" : "Expand context panel"}
            >
              {sceneState.detailsVisible ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
            </button>
          </div>
        </div>

        {sceneState.detailsVisible ? (
          <div className="globe-inspector__content">
        {browseOpen ? (
        <div className="globe-panel">
          <div className="globe-panel__header">
            <div>
              <p className="globe-panel__label">
                {sceneId === "overview"
                  ? "Operational Focus"
                  : sceneId === "intel"
                    ? "Regional Nodes"
                    : "Focus Targets"}
              </p>
            </div>
          </div>
          <div id="globe-browse-panel" className="globe-target-list">
            {visibleFocusTargets.map((target) => (
              <button
                key={target.id}
                type="button"
                onClick={() => {
                  setSelectedId(target.id);
                }}
                className={
                  target.id === selectedId
                    ? "globe-target globe-target--active"
                    : "globe-target"
                }
              >
                <span>{target.label || target.id}</span>
                <span className="globe-target__meta">
                  {getFocusTargetMeta(sceneId, target)}
                </span>
              </button>
            ))}
          </div>
        </div>
        ) : null}

        <div className="globe-panel globe-panel--compact globe-inspector__selection" data-testid="globe-inspector">
          <p className="globe-panel__label">
            {sceneId === "overview"
              ? "Selected Focus"
              : sceneId === "intel"
                ? "Selected Region"
                : "Selected Signal"}
          </p>
          <p className="globe-panel__metric">
            {selectedFocus?.label || "No focus selected"}
          </p>
          <p className="globe-panel__copy">
            {selectedFeatureIsIntel
              ? getSelectedIntelCopy(selectedFeature, sceneState.intelLens)
              : selectedFocus
                ? `${String(selectedFocus.kind || "signal").toUpperCase()} • ${selectedFocus.category || "unknown"}`
                : "Select an object on the globe, or use Browse items for a keyboard-accessible list."}
          </p>
          {selectedFeature ? (
            <div className="globe-detail-grid">
              {String(asRecord(selectedFeature.properties)?.theater || "") ? (
                <div className="globe-detail-row">
                  <span className="globe-detail-row__label">Theater</span>
                  <span className="globe-detail-row__value">
                    {String(asRecord(selectedFeature.properties)?.theater)}
                  </span>
                </div>
              ) : null}
              {String(asRecord(selectedFeature.properties)?.channel || "") ? (
                <div className="globe-detail-row">
                  <span className="globe-detail-row__label">Highlight</span>
                  <span className="globe-detail-row__value">
                    {formatDisplayLabel(asRecord(selectedFeature.properties)?.channel)}
                  </span>
                </div>
              ) : null}
            </div>
          ) : null}
          {getSelectedHeadlines(selectedFeature).length ? (
            <>
              <p className="globe-panel__label">Quick report</p>
              <ul className="globe-target-list">
                {getSelectedHeadlines(selectedFeature).map((item) => (
                  <li key={item.title} className="globe-target">
                    <span>{item.title}</span>
                    <span className="globe-target__meta">{item.source || "Source not listed"}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {selectedProvenanceRows.length ? (
            <>
              <p className="globe-panel__label">Provenance</p>
              <div className="globe-detail-grid">
                {selectedProvenanceRows.map((row) => (
                  <div key={`${row.label}-${row.value}`} className="globe-detail-row">
                    <span className="globe-detail-row__label">{row.label}</span>
                    <span className="globe-detail-row__value">{row.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : null}
          {selectedDetailRows.length ? (
            <>
              <p className="globe-panel__label">Signal Detail</p>
              <div className="globe-detail-grid">
                {selectedDetailRows.map((row) => (
                  <div key={`${row.label}-${row.value}`} className="globe-detail-row">
                    <span className="globe-detail-row__label">{row.label}</span>
                    <span className="globe-detail-row__value">{row.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : null}
          {selectedFeatureIsIntel && selectedEmotionMix.length ? (
            <div className="mt-4 space-y-3">
              <div>
                <p className="globe-panel__label">Regional Emotion Mix</p>
                <div className="mt-2 space-y-2">
                  {selectedEmotionMix.map((entry) => {
                    const maxCount = Math.max(...selectedEmotionMix.map((item) => item.count), 1);
                    return (
                      <div key={entry.emotion} className="space-y-1">
                        <div className="flex items-center justify-between text-[11px] text-slate-300">
                          <span>{formatDisplayLabel(entry.emotion)}</span>
                          <span>{entry.count}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-900/80">
                          <div
                            className="h-1.5 rounded-full"
                            style={{
                              width: `${Math.max(10, (entry.count / maxCount) * 100)}%`,
                              backgroundColor: getEmotionAccent(entry.emotion)
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
              {selectedContextMix.length ? (
                <div>
                  <p className="globe-panel__label">Conflict Triggers</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedContextMix.map((entry) => (
                      <span key={entry.name} className="globe-badge">
                        {formatDisplayLabel(entry.name)} {entry.count}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {selectedImpactMix.length ? (
                <div>
                  <p className="globe-panel__label">Impacted Markets</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {selectedImpactMix.map((entry) => (
                      <span key={entry.name} className="globe-badge">
                        {formatDisplayLabel(entry.name)} {entry.count}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="globe-overlay__actions">
            {selectedFocus ? (
              <button
                type="button"
                onClick={() => setCameraPreset(sceneState.cameraPreset === "focus" ? "free" : "focus")}
                className="globe-action-button"
              >
                {sceneState.cameraPreset === "focus" ? "Return To Free Orbit" : "Follow Selection"}
              </button>
            ) : null}
            <button type="button" onClick={refresh} className="globe-action-button">
              Refresh Scene
            </button>
          </div>
        </div>

        <details className="globe-inspector__advanced">
          <summary>More context, legend, and client scope</summary>
          <div className="globe-inspector__advanced-grid">
        <div className="globe-panel globe-panel--compact">
          <p className="globe-panel__label">Visible Aggregate</p>
          <div className="globe-detail-grid">
            {aggregateRows.map((row) => (
              <div key={`${row.label}-${row.value}`} className="globe-detail-row">
                <span className="globe-detail-row__label">{row.label}</span>
                <span className="globe-detail-row__value">{row.value}</span>
              </div>
            ))}
          </div>
          {sceneLegendEntries.length ? (
            <>
              <p className="globe-panel__label">Color Key</p>
              <div className="globe-legend">
                {sceneLegendEntries.map((entry, index) => (
                  <span key={`${entry.label}-${index}`} className="globe-legend__item">
                    <span
                      className="globe-legend__swatch"
                      style={{ backgroundColor: entry.color }}
                      aria-hidden="true"
                    />
                    <span>{entry.label}</span>
                  </span>
                ))}
              </div>
            </>
          ) : null}
        </div>
        {sceneId === "overview" ? (
          <div className="globe-panel globe-panel--compact globe-client-context">
            <div className="globe-panel__header">
              <div>
                <p className="globe-panel__label">Client Context</p>
                <p className="globe-panel__metric">
                  {clientContext.clientCount} clients / {clientContext.accountCount} accounts
                </p>
              </div>
              <span className="globe-badge">{clientContext.holdingsCount} holdings</span>
            </div>
            <div className="globe-client-context__grid">
              {clientContext.topClients.length ? (
                clientContext.topClients.map((client) => (
                  <a
                    key={client.client_id}
                    href={`/clients?client=${encodeURIComponent(client.client_id)}`}
                    className="globe-client-context__row"
                  >
                    <span>{client.name}</span>
                    <small>
                      {client.accounts_count || 0} accounts / {client.risk_profile || "Unprofiled"}
                    </small>
                  </a>
                ))
              ) : (
                <p className="globe-panel__copy globe-panel__copy--subtle">
                  No client workspaces available yet.
                </p>
              )}
            </div>
          </div>
        ) : null}
          </div>
        </details>
          </div>
        ) : null}
      </div>
    </div>
  );
}
