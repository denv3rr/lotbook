import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadMapLibre, mapLibreWorkerUrl } from "../lib/maplibre";
import type { MapLibre } from "../lib/maplibre";
import type { Map as MapInstance, GeoJSONSource } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import { loadLeaflet, type LeafletLib } from "../lib/leaflet";
import { Card } from "../components/ui/Card";
import { Collapsible } from "../components/ui/Collapsible";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { KpiCard } from "../components/ui/KpiCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { apiGet, apiPost, useApi } from "../lib/api";
import { useMeasuredSize } from "../lib/useMeasuredSize";
import { useTrackerPause } from "../lib/trackerPause";
import { useTrackerStream } from "../lib/stream";
import {
  checkWorkerClass,
  preflightWorkerScript,
  preflightMapResources,
  preflightStyle
} from "../lib/mapDiagnostics";

const MAP_STATE_KEY = "clear_tracker_map_state";
const LEAFLET_POINT_CAP = 240;

function formatLeafletTooltip(point: {
  id?: string;
  kind?: string;
  label?: string;
  category?: string;
  operator?: string | null;
  operator_name?: string | null;
}) {
  const label = point.label || point.id || "Tracker";
  const kind = String(point.kind || "signal").toUpperCase();
  const category = point.category || "unknown";
  const operator = point.operator_name || point.operator;
  return operator
    ? `${label} • ${kind} • ${category} • ${operator}`
    : `${label} • ${kind} • ${category}`;
}

type MapState = {
  center: [number, number];
  zoom: number;
  follow: boolean;
  lock: boolean;
  kinds: {
    flights: boolean;
    ships: boolean;
  };
  categories: string[];
  operators: string[];
  layers: {
    live: boolean;
    history: boolean;
  };
};

type MapStateBoot = MapState & {
  hasView: boolean;
};

function loadMapState(): Partial<MapState> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(MAP_STATE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<MapState>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

type TrackerSnapshot = {
  count: number;
  warnings: string[];
  points: {
    id?: string;
    kind: string;
    label: string;
    category: string;
    lat?: number;
    lon?: number;
    country?: string | null;
    operator?: string | null;
    operator_name?: string | null;
    flight_number?: string | null;
    tail_number?: string | null;
  }[];
};

type SearchResult = {
  count: number;
  points: {
    id: string;
    kind: string;
    label: string;
    category: string;
    operator?: string | null;
    operator_name?: string | null;
    flight_number?: string | null;
  }[];
};

type HistoryPoint = {
  ts: number;
  lat: number;
  lon: number;
  speed_kts: number | null;
};

type TrackerHistory = {
  id: string;
  history: HistoryPoint[];
  summary?: {
    points?: number;
    distance_km?: number;
    start?: { lat: number; lon: number; ts: number };
    end?: { lat: number; lon: number; ts: number };
    direction?: string;
    bearing_deg?: number;
    avg_speed_kts?: number | null;
    avg_altitude_ft?: number | null;
    duration_sec?: number | null;
    route_hint?: string;
  };
};

type TrackerDetail = {
  id: string;
  point?: {
    id?: string;
    label?: string;
    category?: string;
    kind?: string;
    icao24?: string | null;
    callsign?: string | null;
    operator?: string | null;
    operator_name?: string | null;
    flight_number?: string | null;
    tail_number?: string | null;
    country?: string | null;
    altitude_ft?: number | null;
    speed_kts?: number | null;
  };
  history: HistoryPoint[];
  summary?: TrackerHistory["summary"];
};

type GeofenceInput = {
  id?: string;
  label?: string;
  lat: number;
  lon: number;
  radius_km: number;
};

type GeofenceEvent = {
  geofence_id: string;
  geofence_label: string;
  event: "enter" | "exit";
  ts: number;
  lat: number;
  lon: number;
  distance_km: number;
};

type TrackerAnalysis = {
  id: string;
  window_sec: number;
  point_count: number;
  replay: HistoryPoint[];
  loiter: {
    detected: boolean;
    center?: { lat: number; lon: number };
    radius_km?: number;
    max_distance_km?: number;
    duration_sec?: number | null;
    start_ts?: number | null;
    end_ts?: number | null;
  };
  geofences: {
    events: GeofenceEvent[];
    active: string[];
  };
  warnings?: string[];
  meta?: {
    warnings?: string[];
  };
};

export function TrackersPanel() {
  const [mode, setMode] = useState<"combined" | "flights" | "ships">("combined");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [includeCommercial, setIncludeCommercial] = useState(false);
  const [includePrivate, setIncludePrivate] = useState(false);
  const [countryFilter, setCountryFilter] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [idFilter, setIdFilter] = useState("");
  const { paused } = useTrackerPause();
  const serverFiltersActive =
    categoryFilter !== "all" ||
    countryFilter.trim().length > 0 ||
    operatorFilter.trim().length > 0;
  const streamEnabled = !paused && !serverFiltersActive;
  const {
    data: streamData,
    connected,
    error: streamError,
    warnings: streamWarnings
  } = useTrackerStream<TrackerSnapshot>({
    interval: 5,
    mode,
    enabled: streamEnabled
  });
  const streamStatus = paused
    ? {
        state: "paused" as const,
        title: "Stream disabled",
        detail: "Tracking is paused. Resume trackers to reconnect the live feed."
      }
    : serverFiltersActive
      ? {
          state: "filters" as const,
          title: "Stream disabled",
          detail:
            "Server filters are active. Category, country, or operator filters use snapshot polling instead of the live stream."
        }
      : connected
        ? {
            state: "live" as const,
            title: "Live stream connected",
            detail: "Receiving tracker updates over the WebSocket feed."
          }
        : {
            state: "offline" as const,
            title: "Streaming offline",
            detail: "Polling snapshots until the live stream reconnects."
          };
  const snapshotPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set("mode", mode);
    if (categoryFilter !== "all") {
      params.set("category", categoryFilter);
    }
    if (countryFilter.trim()) {
      params.set("country", countryFilter.trim());
    }
    if (operatorFilter.trim()) {
      params.set("operator", operatorFilter.trim());
    }
    return `/api/trackers/snapshot?${params.toString()}`;
  }, [mode, categoryFilter, countryFilter, operatorFilter]);
  const pollEnabled = !paused && (!streamEnabled || !connected);
  const {
    data: pollData,
    error: pollError,
    warnings: pollWarnings,
    refresh: refreshPoll
  } = useApi<TrackerSnapshot>(snapshotPath, {
    interval: pollEnabled ? 20000 : 0,
    enabled: pollEnabled
  });
  const data = streamData || pollData;
  const points = data?.points || [];
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TrackerDetail | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysis, setAnalysis] = useState<TrackerAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisWindowSec, setAnalysisWindowSec] = useState(3600);
  const [loiterRadiusKm, setLoiterRadiusKm] = useState(10);
  const [loiterMinMinutes, setLoiterMinMinutes] = useState(20);
  const [geofences, setGeofences] = useState<GeofenceInput[]>([]);
  const [geofenceDraft, setGeofenceDraft] = useState({
    label: "",
    lat: "",
    lon: "",
    radius: ""
  });
  const [geofenceError, setGeofenceError] = useState<string | null>(null);
  const history = detail ? { id: detail.id, history: detail.history, summary: detail.summary } : null;
  const analysisParamsRef = useRef({
    windowSec: analysisWindowSec,
    loiterRadiusKm,
    loiterMinMinutes,
    geofences
  });
  const { ref: mapRef, size: mapSize } = useMeasuredSize<HTMLDivElement>();
  const mapInstance = useRef<MapInstance | null>(null);
  const [maplibre, setMapLibre] = useState<MapLibre | null>(null);
  const styleRequested = useRef(false);
  const styleLoaded = useRef(false);
  const layersReadyRef = useRef(false);
  const mapReadyRef = useRef(false);
  const mapErrorRef = useRef<string | null>(null);
  const styleDataSeenRef = useRef(false);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapStatus, setMapStatus] = useState("Initializing map...");
  const [mapDiagnostics, setMapDiagnostics] = useState<string[]>([]);
  const [leaflet, setLeaflet] = useState<LeafletLib | null>(null);
  const leafletMap = useRef<ReturnType<LeafletLib["map"]> | null>(null);
  const leafletLayer = useRef<ReturnType<LeafletLib["layerGroup"]> | null>(null);
  const leafletHistoryLayer = useRef<ReturnType<LeafletLib["layerGroup"]> | null>(null);
  const [leafletStatus, setLeafletStatus] = useState("Initializing map...");
  const [mapFallback, setMapFallback] = useState(false);
  const initialMapState = useMemo<MapStateBoot>(() => {
    const stored = loadMapState();
    const hasView =
      Array.isArray(stored.center) &&
      stored.center.length === 2 &&
      typeof stored.zoom === "number";
    return {
      center:
        Array.isArray(stored.center) && stored.center.length === 2
          ? (stored.center as [number, number])
          : ([15, 0] as [number, number]),
      zoom: typeof stored.zoom === "number" ? stored.zoom : 2,
      follow: Boolean(stored.follow),
      lock: Boolean(stored.lock),
      kinds: {
        flights: stored.kinds?.flights !== false,
        ships: stored.kinds?.ships !== false
      },
      categories: Array.isArray(stored.categories) ? stored.categories : [],
      operators: Array.isArray(stored.operators) ? stored.operators : [],
      layers: {
        live: stored.layers?.live !== false,
        history: stored.layers?.history !== false
      },
      hasView
    };
  }, []);
  const [mapFollow, setMapFollow] = useState(initialMapState.follow);
  const [mapLock, setMapLock] = useState(initialMapState.lock);
  const [mapKinds, setMapKinds] = useState(initialMapState.kinds);
  const [mapCategories, setMapCategories] = useState<string[]>(
    initialMapState.categories
  );
  const [mapOperators, setMapOperators] = useState<string[]>(
    initialMapState.operators
  );
  const [mapLayers, setMapLayers] = useState(initialMapState.layers);
  const mapViewRef = useRef<{ center: [number, number]; zoom: number }>({
    center: initialMapState.center,
    zoom: initialMapState.zoom
  });
  const mapAutoFitRef = useRef(
    initialMapState.hasView || initialMapState.lock || initialMapState.follow
  );
  const programmaticMoveRef = useRef(false);
  const mapFollowRef = useRef(mapFollow);
  const [riskOpen, setRiskOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(true);
  const [feedOpen, setFeedOpen] = useState(false);
  const accentColor = "#48f1a6";
  const preferLeaflet = false;

  useEffect(() => {
    if (!paused) {
      refreshPoll();
    }
  }, [paused, refreshPoll]);

  useEffect(() => {
    mapFollowRef.current = mapFollow;
    if (mapFollow) {
      setMapLock(false);
    }
  }, [mapFollow]);

  useEffect(() => {
    if (mapLock) {
      setMapFollow(false);
    }
  }, [mapLock]);

  const searchPath = useMemo(() => {
    const kindParam = mode === "combined" ? "" : `&kind=${mode === "ships" ? "ship" : "flight"}`;
    return `/api/trackers/search?q=${encodeURIComponent(query)}&limit=12&mode=${mode}${kindParam}`;
  }, [query, mode]);
  const {
    data: searchResults,
    error: searchError,
    warnings: searchWarnings
  } = useApi<SearchResult>(searchPath, {
    enabled: query.trim().length > 1
  });
  const filteredSearchResults = useMemo(() => {
    if (!searchResults) return null;
    let next = searchResults.points;
    if (!includeCommercial) {
      next = next.filter((point) => !(point.kind === "flight" && point.category === "commercial"));
    }
    if (!includePrivate) {
      next = next.filter((point) => !(point.kind === "flight" && point.category === "private"));
    }
    if (categoryFilter !== "all") {
      next = next.filter((point) => point.category === categoryFilter);
    }
    return { ...searchResults, points: next, count: next.length };
  }, [searchResults, includeCommercial, includePrivate, categoryFilter]);
  const authHint = "Check CLEAR_WEB_API_KEY + localStorage clear_api_key.";
  const errorMessages = [
    paused ? "Tracker updates paused." : null,
    pollError
      ? `Tracker snapshot failed: ${pollError}${
          pollError.includes("401") || pollError.includes("403") ? ` (${authHint})` : ""
        }`
      : null,
    ...pollWarnings.map((warning) => `Tracker snapshot: ${warning}`),
    streamError ? `Tracker stream failed: ${streamError}` : null,
    ...streamWarnings.map((warning) => `Tracker stream: ${warning}`),
    searchError ? `Search failed: ${searchError}` : null,
    ...searchWarnings.map((warning) => `Search: ${warning}`)
  ].filter(Boolean) as string[];
  const filteredPoints = useMemo(() => {
    let next = points;
    if (mode !== "combined") {
      const wanted = mode === "ships" ? "ship" : "flight";
      next = next.filter((point) => point.kind === wanted);
    }
    if (!includeCommercial) {
      next = next.filter((point) => !(point.kind === "flight" && point.category === "commercial"));
    }
    if (!includePrivate) {
      next = next.filter((point) => !(point.kind === "flight" && point.category === "private"));
    }
    if (categoryFilter !== "all") {
      next = next.filter((point) => point.category === categoryFilter);
    }
    if (countryFilter.trim()) {
      const needle = countryFilter.trim().toLowerCase();
      next = next.filter((point) => (point.country || "").toLowerCase().includes(needle));
    }
    if (operatorFilter.trim()) {
      const needle = operatorFilter.trim().toLowerCase();
      next = next.filter((point) => {
        const op = point.operator || "";
        const opName = point.operator_name || "";
        return op.toLowerCase().includes(needle) || opName.toLowerCase().includes(needle);
      });
    }
    if (idFilter.trim()) {
      const needle = idFilter.trim().toLowerCase();
      next = next.filter((point) => {
        const label = point.label || "";
        const id = point.id || "";
        const flight = point.flight_number || "";
        const tail = point.tail_number || "";
        return (
          label.toLowerCase().includes(needle) ||
          id.toLowerCase().includes(needle) ||
          flight.toLowerCase().includes(needle) ||
          tail.toLowerCase().includes(needle)
        );
      });
    }
    return next;
  }, [
    points,
    mode,
    includeCommercial,
    includePrivate,
    categoryFilter,
    countryFilter,
    operatorFilter,
    idFilter
  ]);
  const categories = useMemo(() => {
    const entries = Array.from(new Set(points.map((point) => point.category).filter(Boolean)));
    const reserved = ["military", "government"];
    const sorted = entries.filter((entry) => !reserved.includes(entry)).sort();
    const list = ["all", ...reserved, ...sorted];
    return Array.from(new Set(list));
  }, [points]);
  const mapOperatorOptions = useMemo(() => {
    const entries = Array.from(
      new Set(
        filteredPoints
          .map((point) => point.operator_name || point.operator)
          .filter((value): value is string => Boolean(value && value.trim()))
      )
    );
    return entries.map((value) => value.trim()).sort();
  }, [filteredPoints]);
  const mapFilteredPoints = useMemo(() => {
    let next = filteredPoints;
    if (!mapKinds.flights) {
      next = next.filter((point) => point.kind !== "flight");
    }
    if (!mapKinds.ships) {
      next = next.filter((point) => point.kind !== "ship");
    }
    if (mapCategories.length > 0) {
      const wanted = new Set(mapCategories.map((value) => value.toLowerCase()));
      next = next.filter((point) => wanted.has(String(point.category || "").toLowerCase()));
    }
    if (mapOperators.length > 0) {
      const wanted = new Set(mapOperators.map((value) => value.toLowerCase()));
      next = next.filter((point) =>
        wanted.has(
          String(point.operator_name || point.operator || "").toLowerCase()
        )
      );
    }
    return next;
  }, [filteredPoints, mapKinds, mapCategories, mapOperators]);
  const mapCategoryOptions = useMemo(
    () => categories.filter((category) => category !== "all"),
    [categories]
  );
  const toggleMapOperator = useCallback((operator: string) => {
    setMapOperators((prev) =>
      prev.includes(operator)
        ? prev.filter((value) => value !== operator)
        : [...prev, operator]
    );
  }, []);
  const toggleMapCategory = useCallback((category: string) => {
    setMapCategories((prev) =>
      prev.includes(category)
        ? prev.filter((value) => value !== category)
        : [...prev, category]
    );
  }, []);
  const followTarget = useMemo(() => {
    if (!selectedId || !mapLayers.live) return null;
    const needle = selectedId.toLowerCase();
    return mapFilteredPoints.find(
      (point) => String(point.id || "").toLowerCase() === needle
    );
  }, [mapFilteredPoints, mapLayers.live, selectedId]);
  const mapFocusStatus = useMemo(() => {
    if (mapFollow) {
      if (!mapLayers.live) return "Live layer hidden.";
      if (!followTarget) return "Follow target missing.";
      return `Following ${followTarget.label || followTarget.id || "target"}.`;
    }
    if (mapLock) return "View locked.";
    return "Auto-fit runs on first load only.";
  }, [followTarget, mapFollow, mapLayers.live, mapLock]);
  const riskTotals = useMemo(() => {
    const counts = filteredPoints.reduce(
      (acc, point) => {
        if (point.kind === "flight") acc.flights += 1;
        if (point.kind === "ship") acc.ships += 1;
        return acc;
      },
      { flights: 0, ships: 0 }
    );
    const categoryMap = filteredPoints.reduce<Record<string, number>>((acc, point) => {
      const key = point.category || "unknown";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    const topCategories = Object.entries(categoryMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
    return { counts, topCategories };
  }, [filteredPoints]);

  const trackerGeojson = useMemo<FeatureCollection>(() => {
    return {
      type: "FeatureCollection",
      features: mapFilteredPoints
        .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
        .map((point) => ({
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [point.lon as number, point.lat as number]
          },
          properties: {
            id: point.id || "",
            kind: point.kind,
            label: point.label,
            category: point.category
          }
        }))
    };
  }, [mapFilteredPoints]);

  const persistMapState = useCallback(
    (overrides?: Partial<MapState>) => {
      if (typeof window === "undefined") return;
      const payload: MapState = {
        center: mapViewRef.current.center,
        zoom: mapViewRef.current.zoom,
        follow: mapFollow,
        lock: mapLock,
        kinds: mapKinds,
        categories: mapCategories,
        operators: mapOperators,
        layers: mapLayers,
        ...overrides
      };
      window.localStorage.setItem(MAP_STATE_KEY, JSON.stringify(payload));
    },
    [mapFollow, mapLock, mapKinds, mapCategories, mapOperators, mapLayers]
  );

  useEffect(() => {
    persistMapState();
  }, [persistMapState]);

  useEffect(() => {
    setMapCategories((prev) =>
      prev.filter((value) => categories.includes(value))
    );
  }, [categories]);

  useEffect(() => {
    setMapOperators((prev) =>
      prev.filter((value) =>
        mapOperatorOptions.some(
          (option) => option.toLowerCase() === value.toLowerCase()
        )
      )
    );
  }, [mapOperatorOptions]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    if (paused) {
      setDetail(null);
      return;
    }
    apiGet<TrackerDetail>(`/api/trackers/detail/${encodeURIComponent(selectedId)}`, 0)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [selectedId, paused]);

  useEffect(() => {
    analysisParamsRef.current = {
      windowSec: analysisWindowSec,
      loiterRadiusKm,
      loiterMinMinutes,
      geofences
    };
  }, [analysisWindowSec, loiterRadiusKm, loiterMinMinutes, geofences]);

  const runAnalysis = useCallback(async () => {
    if (!selectedId || paused) return;
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const params = analysisParamsRef.current;
      const payload = await apiPost<TrackerAnalysis>("/api/trackers/analysis", {
        tracker_id: selectedId,
        window_sec: Math.max(60, Math.floor(params.windowSec || 0)),
        loiter_radius_km: Math.max(0.1, params.loiterRadiusKm || 0),
        loiter_min_minutes: Math.max(1, params.loiterMinMinutes || 0),
        geofences: params.geofences
      });
      setAnalysis(payload);
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : "Analysis failed.");
      setAnalysis(null);
    } finally {
      setAnalysisLoading(false);
    }
  }, [selectedId, paused]);

  useEffect(() => {
    if (!selectedId || paused) {
      setAnalysis(null);
      setAnalysisError(null);
      return;
    }
    runAnalysis();
  }, [selectedId, paused, runAnalysis]);

  const addGeofence = useCallback(() => {
    const lat = Number(geofenceDraft.lat);
    const lon = Number(geofenceDraft.lon);
    const radius = Number(geofenceDraft.radius);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setGeofenceError("Latitude and longitude must be valid numbers.");
      return;
    }
    if (!Number.isFinite(radius) || radius <= 0) {
      setGeofenceError("Radius must be a positive number.");
      return;
    }
    const label = geofenceDraft.label.trim();
    setGeofences((prev) => [
      ...prev,
      {
        label: label || `Fence ${prev.length + 1}`,
        lat,
        lon,
        radius_km: radius
      }
    ]);
    setGeofenceDraft({ label: "", lat: "", lon: "", radius: "" });
    setGeofenceError(null);
  }, [geofenceDraft]);

  const exportAnalysis = useCallback(() => {
    if (!analysis) return;
    const payload = JSON.stringify(analysis, null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `tracker_analysis_${analysis.id}_${stamp}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }, [analysis]);

  const mapInitRef = useRef(false);
  const mapActiveRef = useRef(true);
  const mapResizeHandler = useRef<(() => void) | null>(null);
  const recordLeafletView = useCallback(() => {
    if (!leafletMap.current) return;
    const center = leafletMap.current.getCenter();
    mapViewRef.current = { center: [center.lat, center.lng], zoom: leafletMap.current.getZoom() };
    persistMapState();
  }, [persistMapState]);
  const recordMapLibreView = useCallback(() => {
    if (!mapInstance.current) return;
    const center = mapInstance.current.getCenter();
    mapViewRef.current = { center: [center.lat, center.lng], zoom: mapInstance.current.getZoom() };
    persistMapState();
  }, [persistMapState]);
  const markProgrammaticMove = useCallback(() => {
    programmaticMoveRef.current = true;
    window.setTimeout(() => {
      programmaticMoveRef.current = false;
    }, 250);
  }, []);
  const handleMapFit = useCallback(() => {
    const points = mapFilteredPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon)
    );
    if (!points.length) return;
    if (mapFallback && leafletMap.current && leaflet) {
      const bounds = leaflet.latLngBounds(
        points.map((point) => [point.lat as number, point.lon as number])
      );
      markProgrammaticMove();
      leafletMap.current.fitBounds(bounds, { padding: [30, 30], maxZoom: 5 });
      mapAutoFitRef.current = true;
      return;
    }
    if (!mapFallback && mapInstance.current && mapReady && maplibre) {
      const bounds = points.reduce(
        (box, point) => box.extend([point.lon as number, point.lat as number]),
        new maplibre.LngLatBounds(
          [points[0].lon as number, points[0].lat as number],
          [points[0].lon as number, points[0].lat as number]
        )
      );
      markProgrammaticMove();
      mapInstance.current.fitBounds(bounds, { padding: 80, maxZoom: 6 });
    }
  }, [leaflet, mapFallback, mapFilteredPoints, markProgrammaticMove, mapReady, maplibre]);

  useEffect(() => {
    let mounted = true;
    if (preferLeaflet) {
      setMapFallback(true);
      setMapStatus("Loading fallback map engine...");
      return () => {
        mounted = false;
      };
    }
    loadMapLibre()
      .then((lib) => {
        if (mounted) {
          setMapLibre(lib);
        }
      })
      .catch(() => {
        if (!mounted) return;
        setMapError("Map engine failed to load.");
        setMapStatus("Map engine failed.");
        setMapFallback(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    if (!mapFallback || leaflet) {
      return () => {
        mounted = false;
      };
    }
    setLeafletStatus("Loading fallback map engine...");
    loadLeaflet()
      .then((lib) => {
        if (!mounted) return;
        setLeaflet(lib);
        setLeafletStatus("Leaflet engine ready.");
      })
      .catch(() => {
        if (!mounted) return;
        setLeafletStatus("Leaflet engine failed.");
        setMapError("Leaflet map engine failed to load.");
      });
    return () => {
      mounted = false;
    };
  }, [leaflet, mapFallback]);

  useEffect(() => {
    if (mapFallback) return;
    let raf = 0;
    let timeout = 0;
    let readyInterval = 0;
    const initMap = () => {
      if (mapInitRef.current || mapInstance.current) return;
      if (!mapRef.current) {
        raf = window.requestAnimationFrame(initMap);
        return;
      }
      if (!maplibre) {
        setMapStatus("Loading map engine...");
        raf = window.requestAnimationFrame(initMap);
        return;
      }
      const rect = mapRef.current.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) {
        setMapStatus("Waiting for map container...");
        raf = window.requestAnimationFrame(initMap);
        return;
      }
      mapInitRef.current = true;
      const canvas = document.createElement("canvas");
      let hasWebgl = false;
      try { hasWebgl = !!window.WebGL2RenderingContext && !!canvas.getContext("webgl2"); }
      catch { /* A denied GPU context must take the same fallback path. */ }
      if (!hasWebgl) {
        setMapError("WebGL 2 is not supported in this browser. Use the fallback map.");
        setMapStatus("WebGL 2 not supported.");
        mapInitRef.current = false;
        setMapFallback(true);
        return;
      }
      setMapStatus("Booting map engine...");
    const diagnostics: string[] = [];
    diagnostics.push(checkWorkerClass(maplibre));
    setMapDiagnostics(diagnostics);
    preflightWorkerScript(mapLibreWorkerUrl).then((line) => {
      if (!mapActiveRef.current) return;
      setMapDiagnostics((prev) => {
        const next = prev.filter((item) => !item.startsWith("Worker script"));
        next.push(line);
        return next;
      });
    });
    mapActiveRef.current = true;
    const styleUrl =
      "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
    preflightStyle(styleUrl).then((result) => {
      if (!mapActiveRef.current) return;
      setMapDiagnostics((prev) => {
        const next = prev.filter((item) => !item.startsWith("Style:"));
        next.push(`Style: ${result.ok ? "ok" : result.detail}`);
        return next;
      });
    });
    preflightMapResources(styleUrl).then((resourceLines) => {
      if (!mapActiveRef.current) return;
      setMapDiagnostics((prev) => {
        const next = prev.filter(
          (item) =>
            !item.startsWith("Sprite") &&
            !item.startsWith("Glyphs") &&
            !item.startsWith("Tile")
        );
        return [...next, ...resourceLines];
      });
    });
      let map: MapInstance;
      try {
        map = new maplibre.Map({
          container: mapRef.current,
          style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
          center: [mapViewRef.current.center[1], mapViewRef.current.center[0]],
          zoom: mapViewRef.current.zoom,
          attributionControl: false,
          transformRequest: (url, resourceType) => {
            if (resourceType === "Style" && !styleRequested.current) {
              styleRequested.current = true;
              setMapStatus("Requesting style...");
            }
            return { url };
          }
        });
      } catch (err) {
        setMapError(err instanceof Error ? err.message : "Map initialization failed.");
        setMapStatus("Map init failed.");
        mapInitRef.current = false;
        setMapFallback(true);
        return;
      }
      setMapStatus("Map instance created.");
      map.addControl(new maplibre.NavigationControl({ visualizePitch: true }), "top-right");
      const handleMapMoveStart = () => {
        if (programmaticMoveRef.current) return;
        if (!mapFollowRef.current) {
          setMapLock(true);
        }
      };
      map.on("movestart", handleMapMoveStart);
      map.on("moveend", recordMapLibreView);
      map.on("zoomend", recordMapLibreView);
      map.on("styledata", () => {
        styleDataSeenRef.current = true;
        setMapStatus("Loading style and tiles...");
      });
      const initLayers = () => {
        if (layersReadyRef.current) return;
        layersReadyRef.current = true;
        map.addSource("tracker-points", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] }
        });
        map.addLayer({
          id: "tracker-points-glow",
          type: "circle",
          source: "tracker-points",
          paint: {
            "circle-radius": 6,
            "circle-color": accentColor,
            "circle-opacity": 0.12
          }
        });
        map.addLayer({
          id: "tracker-points-layer",
          type: "circle",
          source: "tracker-points",
          paint: {
            "circle-radius": 3,
            "circle-color": [
              "match",
              ["get", "kind"],
              "ship",
              "#8892a0",
              accentColor
            ],
            "circle-opacity": 0.8
          }
        });
        map.on("mouseenter", "tracker-points-layer", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "tracker-points-layer", () => {
          map.getCanvas().style.cursor = "";
        });
        map.on("click", "tracker-points-layer", (event: {
          features?: Array<{ properties?: { id?: unknown } }>;
        }) => {
          const feature = event.features?.[0];
          const id = feature?.properties?.id;
          if (typeof id === "string" && id) {
            setSelectedId(id);
            setFeedOpen(true);
          }
        });
        map.addSource("history-line", {
          type: "geojson",
          data: {
            type: "Feature",
            geometry: { type: "LineString", coordinates: [] },
            properties: {}
          }
        });
        map.addLayer({
          id: "history-line-layer",
          type: "line",
          source: "history-line",
          paint: {
            "line-color": accentColor,
            "line-width": 2,
            "line-opacity": 0.8
          }
        });
      };
      map.on("style.load", () => {
        styleLoaded.current = true;
        setMapStatus("Style loaded.");
        if (!mapReady) {
          setMapReady(true);
          mapReadyRef.current = true;
          setMapError(null);
          mapErrorRef.current = null;
          initLayers();
        }
      });
      map.on("render", () => {
        if (mapReady) {
          setMapStatus("Rendering map.");
        }
      });
      map.on("load", () => {
        setMapReady(true);
        mapReadyRef.current = true;
        setMapError(null);
        mapErrorRef.current = null;
        setMapStatus("Map ready.");
        map.resize();
        window.setTimeout(() => map.resize(), 200);
        initLayers();
      });
      map.on("error", (event: { error?: { message?: string } }) => {
        const message = event?.error?.message;
        const detail = message || "Map data unavailable.";
        setMapError(detail);
        mapErrorRef.current = detail;
        setMapStatus("Map error.");
      });
      map.on("idle", () => {
        if (!mapError) {
          setMapError(null);
          setMapStatus("Map idle.");
        }
      });
      mapInstance.current = map;
      readyInterval = window.setInterval(() => {
        if (!mapActiveRef.current || mapReadyRef.current) return;
        const isStyleLoaded = map.isStyleLoaded ? map.isStyleLoaded() : false;
        const isLoaded = map.loaded ? map.loaded() : false;
        if (isStyleLoaded || isLoaded) {
          setMapReady(true);
          mapReadyRef.current = true;
          setMapError(null);
          mapErrorRef.current = null;
          setMapStatus("Map ready.");
          initLayers();
          map.resize();
          map.triggerRepaint();
          window.clearInterval(readyInterval);
        }
      }, 500);
      timeout = window.setTimeout(() => {
        if (!mapReadyRef.current && !mapErrorRef.current) {
          if (!styleRequested.current) {
            setMapStatus("Style request blocked before fetch.");
          } else if (!styleLoaded.current) {
            setMapStatus("Style requested but never loaded.");
          } else {
            setMapStatus("Map load timeout. Check CSP/worker settings.");
          }
          if (
            styleLoaded.current ||
            (styleDataSeenRef.current && map.isStyleLoaded && map.isStyleLoaded())
          ) {
            setMapReady(true);
            mapReadyRef.current = true;
            setMapError(null);
            mapErrorRef.current = null;
            initLayers();
            map.resize();
            map.triggerRepaint();
          }
        }
      }, 6000);
      const onResize = () => map.resize();
      mapResizeHandler.current = onResize;
      window.addEventListener("resize", onResize);
    };
    initMap();
    return () => {
      window.cancelAnimationFrame(raf);
      window.clearTimeout(timeout);
      window.clearInterval(readyInterval);
    };
  }, [maplibre]);

  useEffect(() => {
    return () => {
      mapActiveRef.current = false;
      if (mapResizeHandler.current) {
        window.removeEventListener("resize", mapResizeHandler.current);
      }
      mapInstance.current?.remove();
      mapInstance.current = null;
      mapInitRef.current = false;
      setMapReady(false);
      mapReadyRef.current = false;
      setMapError(null);
      mapErrorRef.current = null;
      setMapStatus("Initializing map...");
    };
  }, [maplibre]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapReady) return;
    mapInstance.current.resize();
  }, [mapSize.height, mapSize.width, mapReady]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapOpen) return;
    const handle = window.setTimeout(() => mapInstance.current?.resize(), 200);
    return () => window.clearTimeout(handle);
  }, [mapOpen]);

  useEffect(() => {
    if (!mapFallback || !mapRef.current || leafletMap.current || !leaflet) return;
    setLeafletStatus("Booting map engine...");
    const map = leaflet.map(mapRef.current, {
      center: [15, 0],
      zoom: 2,
      zoomControl: true
    });
    map.setView(mapViewRef.current.center, mapViewRef.current.zoom, { animate: false });
    const tiles = leaflet.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        subdomains: "abcd",
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors &copy; CARTO"
      }
    );
    tiles.on("tileerror", () => {
      setLeafletStatus("Tile load error. Check CSP or network.");
      setMapError("Leaflet tile load error.");
    });
    tiles.addTo(map);
    const layer = leaflet.layerGroup().addTo(map);
    const historyLayer = leaflet.layerGroup().addTo(map);
    leafletMap.current = map;
    leafletLayer.current = layer;
    leafletHistoryLayer.current = historyLayer;
    setLeafletStatus("Map ready.");
    setMapReady(true);
    setMapError(null);
    map.invalidateSize();
    recordLeafletView();
    map.on("moveend", recordLeafletView);
    map.on("zoomend", recordLeafletView);
    map.on("movestart", () => {
      if (programmaticMoveRef.current) return;
      if (!mapFollowRef.current) {
        setMapLock(true);
      }
    });
    return () => {
      map.off("moveend", recordLeafletView);
      map.off("zoomend", recordLeafletView);
      map.off("movestart");
      map.remove();
      leafletMap.current = null;
      leafletLayer.current = null;
      leafletHistoryLayer.current = null;
    };
  }, [leaflet, mapFallback, recordLeafletView]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapReady) return;
    const map = mapInstance.current;
    const source = map.getSource("tracker-points") as GeoJSONSource | undefined;
    if (!source) return;
    source.setData(trackerGeojson);
  }, [trackerGeojson, mapReady]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapReady) return;
    const map = mapInstance.current;
    const setVisibility = (layerId: string, visible: boolean) => {
      if (!map.getLayer(layerId)) return;
      map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
    };
    setVisibility("tracker-points-layer", mapLayers.live);
    setVisibility("tracker-points-glow", mapLayers.live);
    setVisibility("history-line-layer", mapLayers.history);
  }, [mapFallback, mapLayers, mapReady]);

  useEffect(() => {
    if (!mapFallback || !leaflet) return;
    if (!leafletLayer.current || !leafletMap.current) return;
    const layer = leafletLayer.current;
    layer.clearLayers();
    if (!mapLayers.live) {
      return;
    }
    const points = mapFilteredPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon)
    );
    points.slice(0, LEAFLET_POINT_CAP).forEach((point) => {
      const color = point.kind === "ship" ? "#8892a0" : "#48f1a6";
      const marker = leaflet.circleMarker([point.lat as number, point.lon as number], {
        radius: 4.5,
        color,
        weight: 1.2,
        opacity: 0.9,
        fillColor: color,
        fillOpacity: 0.75
      });
      marker.bindTooltip(formatLeafletTooltip(point), {
        direction: "top",
        opacity: 0.92,
        sticky: true
      });
      marker.on("click", () => {
        const id = point.id;
        if (!id) return;
        setSelectedId(id);
        setFeedOpen(true);
      });
      marker.addTo(layer);
    });
    if (points.length && !mapLock && !mapFollow && !mapAutoFitRef.current) {
      const bounds = leaflet.latLngBounds(
        points.map((point) => [point.lat as number, point.lon as number])
      );
      markProgrammaticMove();
      leafletMap.current.fitBounds(bounds, { padding: [30, 30], maxZoom: 5 });
      mapAutoFitRef.current = true;
    }
  }, [leaflet, mapFilteredPoints, mapFollow, mapLock, mapLayers.live, markProgrammaticMove]);

  useEffect(() => {
    if (!mapFallback || !leaflet) return;
    if (!leafletHistoryLayer.current || !leafletMap.current) return;
    const layer = leafletHistoryLayer.current;
    layer.clearLayers();
    if (!mapLayers.history) return;
    const coords = (history?.history || [])
      .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
      .map((point) => [point.lat as number, point.lon as number] as [number, number]);
    if (coords.length < 2) return;
    const line = leaflet.polyline(coords, {
      color: accentColor,
      weight: 2,
      opacity: 0.8
    });
    line.addTo(layer);
  }, [accentColor, history, leaflet, mapFallback, mapLayers.history]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapReady || !mapFollow) return;
    if (!mapLayers.live) return;
    if (!followTarget || !Number.isFinite(followTarget.lat) || !Number.isFinite(followTarget.lon)) {
      setMapStatus("Follow target missing.");
      return;
    }
    const map = mapInstance.current;
    markProgrammaticMove();
    map.easeTo({
      center: [followTarget.lon as number, followTarget.lat as number],
      zoom: map.getZoom(),
      duration: 0
    });
  }, [mapFallback, mapReady, mapFollow, followTarget, markProgrammaticMove]);

  useEffect(() => {
    if (!mapFallback || !mapFollow || !leafletMap.current) return;
    if (!followTarget || !Number.isFinite(followTarget.lat) || !Number.isFinite(followTarget.lon)) {
      setLeafletStatus("Follow target missing.");
      return;
    }
    const zoom = leafletMap.current.getZoom();
    markProgrammaticMove();
    leafletMap.current.setView(
      [followTarget.lat as number, followTarget.lon as number],
      zoom,
      { animate: false }
    );
    setLeafletStatus(`Following ${followTarget.label || followTarget.id || "target"}.`);
  }, [mapFallback, mapFollow, followTarget, markProgrammaticMove]);

  useEffect(() => {
    if (!mapFallback) return;
    if (!leafletMap.current || !mapOpen) return;
    const map = leafletMap.current;
    const timeout = window.setTimeout(() => {
      map.invalidateSize();
    }, 150);
    return () => window.clearTimeout(timeout);
  }, [mapOpen]);

  useEffect(() => {
    if (mapFallback) return;
    if (!mapInstance.current || !mapReady) return;
    const map = mapInstance.current;
    if (!map.getSource("history-line")) return;
    const coords = (history?.history || []).map((point) => [point.lon, point.lat]);
    const feature: Feature = {
      type: "Feature",
      geometry: { type: "LineString", coordinates: coords },
      properties: {}
    };
    const source = map.getSource("history-line") as GeoJSONSource;
    source.setData(feature);
    if (maplibre && coords.length >= 2 && !mapLock && !mapFollow && mapLayers.history) {
      const bounds = coords.reduce(
        (box, coord) => box.extend(coord as [number, number]),
        new maplibre.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number])
      );
      map.fitBounds(bounds, { padding: 80, maxZoom: 6 });
    }
  }, [history, mapFollow, mapLock, mapLayers.history, mapReady, maplibre]);

  useEffect(() => {
    if (mapFallback || !mapInstance.current || !mapReady || !mapOpen) return;
    const map = mapInstance.current;
    const timeout = window.setTimeout(() => map.resize(), 150);
    return () => window.clearTimeout(timeout);
  }, [mapOpen, mapReady]);

  return (
    <Card className="rounded-2xl p-5">
      <SectionHeader
        label="TRACKERS"
        title="Live Trackers"
        right={data ? `${data.count} signals` : "Loading"}
      />
      <div className="mt-4">
        <ErrorBanner messages={errorMessages} onRetry={refreshPoll} />
      </div>
      {streamStatus.state === "paused" || streamStatus.state === "filters" ? (
        <div
          className="mt-4 rounded-xl border border-amber-400/30 px-4 py-3 text-xs text-amber-200"
          data-testid="tracker-stream-status"
          role="status"
        >
          <p className="font-semibold">{streamStatus.title}</p>
          <p className="mt-1 text-slate-300">{streamStatus.detail}</p>
        </div>
      ) : (
        <div className="sr-only" data-testid="tracker-stream-status" role="status">
          {streamStatus.title}. {streamStatus.detail}
        </div>
      )}
      <div className="mt-6 space-y-4 text-sm text-slate-300">
        <Collapsible
          title="Global Risk Signals"
          meta={data ? `${riskTotals.counts.flights + riskTotals.counts.ships} active entities` : "Loading"}
          open={riskOpen}
          onToggle={() => setRiskOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            <KpiCard label="Active Flights" value={`${riskTotals.counts.flights}`} tone="text-green-300" />
            <KpiCard label="Active Ships" value={`${riskTotals.counts.ships}`} tone="text-slate-100" />
            <KpiCard label="Signal Density" value={`${points.length}`} tone="text-slate-100" />
          </div>
          <div className="mt-5 grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">Dominant Categories</p>
              <div className="space-y-2">
                {riskTotals.topCategories.length ? (
                  riskTotals.topCategories.map(([category, count]) => (
                    <div key={category} className="flex items-center justify-between">
                      <span className="text-slate-100">{category}</span>
                      <span className="text-green-300">{count}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400">No active categories yet.</p>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-slate-700 p-4">
              <p className="text-xs font-semibold text-slate-200 mb-2">System Status</p>
              <p className="text-sm text-green-300">
                {streamStatus.title}. {streamStatus.detail}
              </p>
              {(data?.warnings || []).length > 0 ? (
                <div className="mt-3 space-y-1 text-xs text-amber-300">
                  {data?.warnings?.map((warn) => (
                    <p key={warn}>{warn}</p>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 mt-2">No feed warnings detected.</p>
              )}
            </div>
          </div>
        </Collapsible>

        <Collapsible
          title="Tracker Map"
          meta={mapFallback ? "Leaflet" : mapReady ? "Map online" : "Initializing"}
          open={mapOpen}
          onToggle={() => setMapOpen((prev) => !prev)}
        >
          <div
            ref={mapRef}
            className="relative h-[420px] overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/60 scanline"
          >
            {!mapReady && !mapError ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-slate-300 bg-slate-950/60">
                Loading map feed...
              </div>
            ) : null}
            {mapError ? (
              <div className="absolute inset-0 z-10 flex items-center justify-center text-xs text-amber-300 bg-slate-950/60">
                {mapError}
              </div>
            ) : null}
            <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-green-400/20 bg-slate-950/80 px-3 py-2 text-xs text-green-300">
              <p>
                {mapFilteredPoints.length
                  ? `${mapFilteredPoints.length} live entities`
                  : "Awaiting live feed"}
              </p>
              <p
                className={
                  streamStatus.state === "live" ? "mt-1 text-green-200" : "mt-1 text-amber-200"
                }
              >
                {streamStatus.title}
              </p>
            </div>
            <div className="absolute bottom-3 right-3 z-10 rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 text-[11px] text-slate-300">
              <p>{mapFallback ? leafletStatus : mapStatus}</p>
              {!mapFallback && mapDiagnostics.length ? (
                <div className="mt-1 space-y-0.5">
                  {mapDiagnostics.map((item, idx) => (
                    <p key={`${idx}-${item}`}>{item}</p>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-700 p-4 space-y-3">
              <div>
                <p className="text-xs font-semibold text-slate-200">Map Focus</p>
                <p className="text-[11px] text-slate-400 mt-1">{mapFocusStatus}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={!selectedId || !mapLayers.live}
                  onClick={() => setMapFollow((prev) => !prev)}
                  className={`rounded-full border px-3 py-1 text-[11px] ${
                    mapFollow
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  } ${selectedId && mapLayers.live ? "" : "opacity-50 cursor-not-allowed"}`}
                >
                  Follow {mapFollow ? "On" : "Off"}
                </button>
                <button
                  type="button"
                  onClick={() => setMapLock((prev) => !prev)}
                  className={`rounded-full border px-3 py-1 text-[11px] ${
                    mapLock
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  }`}
                >
                  Lock View {mapLock ? "On" : "Off"}
                </button>
                <button
                  type="button"
                  onClick={handleMapFit}
                  className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:text-green-200"
                >
                  Fit Bounds
                </button>
              </div>
            </div>
            <div className="rounded-xl border border-slate-700 p-4 space-y-3">
              <p className="text-xs font-semibold text-slate-200">Map Filters</p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setMapKinds((prev) => ({ ...prev, flights: !prev.flights }))
                  }
                  className={`rounded-full border px-3 py-1 text-[11px] ${
                    mapKinds.flights
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  }`}
                >
                  Flights {mapKinds.flights ? "On" : "Off"}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setMapKinds((prev) => ({ ...prev, ships: !prev.ships }))
                  }
                  className={`rounded-full border px-3 py-1 text-[11px] ${
                    mapKinds.ships
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  }`}
                >
                  Ships {mapKinds.ships ? "On" : "Off"}
                </button>
                <button
                  type="button"
                  onClick={() => setMapCategories([])}
                  className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:text-green-200"
                >
                  All Categories
                </button>
                <button
                  type="button"
                  onClick={() => setMapOperators([])}
                  className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-300 hover:text-green-200"
                >
                  All Operators
                </button>
              </div>
              {mapCategoryOptions.length ? (
                <div className="grid grid-cols-2 gap-2 max-h-28 overflow-y-auto text-[11px] text-slate-300">
                  {mapCategoryOptions.map((category) => (
                    <label key={category} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={mapCategories.includes(category)}
                        onChange={() => toggleMapCategory(category)}
                        className="accent-emerald-400"
                      />
                      <span>{category}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-slate-400">No categories available.</p>
              )}
              <div className="pt-2 border-t border-slate-800/60 space-y-2">
                <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
                  Operators
                </p>
                {mapOperatorOptions.length ? (
                  <div className="grid grid-cols-2 gap-2 max-h-28 overflow-y-auto text-[11px] text-slate-300">
                    {mapOperatorOptions.map((operator) => (
                      <label key={operator} className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={mapOperators.includes(operator)}
                          onChange={() => toggleMapOperator(operator)}
                          className="accent-emerald-400"
                        />
                        <span>{operator}</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-400">No operators available.</p>
                )}
              </div>
              <div className="pt-2 border-t border-slate-800/60 space-y-2">
                <p className="text-xs font-semibold text-slate-200">Map Layers</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setMapLayers((prev) => ({ ...prev, live: !prev.live }))
                    }
                    className={`rounded-full border px-3 py-1 text-[11px] ${
                      mapLayers.live
                        ? "border-green-400/70 text-green-200"
                        : "border-slate-700 text-slate-300"
                    }`}
                  >
                    Live Points {mapLayers.live ? "On" : "Off"}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setMapLayers((prev) => ({ ...prev, history: !prev.history }))
                    }
                    className={`rounded-full border px-3 py-1 text-[11px] ${
                      mapLayers.history
                        ? "border-green-400/70 text-green-200"
                        : "border-slate-700 text-slate-300"
                    }`}
                  >
                    History Line {mapLayers.history ? "On" : "Off"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </Collapsible>

        <Collapsible
          title="Tracker Analysis"
          meta={
            selectedId
              ? analysisLoading
                ? "Running..."
                : analysis
                  ? `${analysis.point_count} points`
                  : "Ready"
              : "Select a tracker"
          }
          open={analysisOpen}
          onToggle={() => setAnalysisOpen((prev) => !prev)}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-700 p-4 space-y-3">
              <p className="text-xs font-semibold text-slate-200">
                Analysis Controls
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label
                    htmlFor="analysis-window"
                    className="text-[11px] text-slate-400"
                  >
                    Replay Window (sec)
                  </label>
                  <input
                    id="analysis-window"
                    type="number"
                    min={60}
                    step={60}
                    value={analysisWindowSec}
                    onChange={(event) =>
                      setAnalysisWindowSec(Number(event.target.value) || 0)
                    }
                    className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  />
                </div>
                <div>
                  <label
                    htmlFor="analysis-loiter-radius"
                    className="text-[11px] text-slate-400"
                  >
                    Loiter Radius (km)
                  </label>
                  <input
                    id="analysis-loiter-radius"
                    type="number"
                    min={0.1}
                    step={0.5}
                    value={loiterRadiusKm}
                    onChange={(event) =>
                      setLoiterRadiusKm(Number(event.target.value) || 0)
                    }
                    className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  />
                </div>
                <div>
                  <label
                    htmlFor="analysis-loiter-min"
                    className="text-[11px] text-slate-400"
                  >
                    Loiter Min (min)
                  </label>
                  <input
                    id="analysis-loiter-min"
                    type="number"
                    min={1}
                    step={1}
                    value={loiterMinMinutes}
                    onChange={(event) =>
                      setLoiterMinMinutes(Number(event.target.value) || 0)
                    }
                    className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  />
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 p-3 space-y-2">
                <p className="text-[11px] text-slate-400">Geofences</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={geofenceDraft.label}
                    onChange={(event) =>
                      setGeofenceDraft((prev) => ({
                        ...prev,
                        label: event.target.value
                      }))
                    }
                    className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2 text-xs text-slate-100"
                    placeholder="Label"
                  />
                  <input
                    type="number"
                    value={geofenceDraft.radius}
                    onChange={(event) =>
                      setGeofenceDraft((prev) => ({
                        ...prev,
                        radius: event.target.value
                      }))
                    }
                    className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2 text-xs text-slate-100"
                    placeholder="Radius km"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    type="number"
                    value={geofenceDraft.lat}
                    onChange={(event) =>
                      setGeofenceDraft((prev) => ({
                        ...prev,
                        lat: event.target.value
                      }))
                    }
                    className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2 text-xs text-slate-100"
                    placeholder="Latitude"
                  />
                  <input
                    type="number"
                    value={geofenceDraft.lon}
                    onChange={(event) =>
                      setGeofenceDraft((prev) => ({
                        ...prev,
                        lon: event.target.value
                      }))
                    }
                    className="rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2 text-xs text-slate-100"
                    placeholder="Longitude"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={addGeofence}
                    className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-200 hover:text-green-200"
                  >
                    Add Fence
                  </button>
                  {geofences.length ? (
                    <button
                      type="button"
                      onClick={() => setGeofences([])}
                      className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-400 hover:text-slate-200"
                    >
                      Clear
                    </button>
                  ) : null}
                </div>
                {geofenceError ? (
                  <p className="text-xs text-amber-300">{geofenceError}</p>
                ) : null}
                {geofences.length ? (
                  <div className="space-y-1 text-[11px] text-slate-300">
                    {geofences.map((fence, idx) => (
                      <div
                        key={`${fence.label}-${idx}`}
                        className="flex items-center justify-between"
                      >
                        <span>
                          {fence.label || `Fence ${idx + 1}`} •{" "}
                          {fence.lat.toFixed(2)}, {fence.lon.toFixed(2)} •{" "}
                          {fence.radius_km.toFixed(1)} km
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            setGeofences((prev) =>
                              prev.filter((_, current) => current !== idx)
                            )
                          }
                          className="text-[11px] text-slate-500 hover:text-slate-200"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">
                    Add a fence to log enter/exit events.
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={runAnalysis}
                  disabled={!selectedId || analysisLoading}
                  className={`rounded-full border px-4 py-1 text-[11px] ${
                    analysisLoading
                      ? "border-slate-700 text-slate-500"
                      : "border-green-400/60 text-green-200"
                  }`}
                >
                  {analysisLoading ? "Running..." : "Run Analysis"}
                </button>
                <button
                  type="button"
                  onClick={exportAnalysis}
                  disabled={!analysis}
                  className={`rounded-full border px-4 py-1 text-[11px] ${
                    analysis
                      ? "border-slate-700 text-slate-200 hover:text-green-200"
                      : "border-slate-800 text-slate-500"
                  }`}
                >
                  Export JSON
                </button>
              </div>
              {analysisError ? (
                <p className="text-xs text-amber-300">{analysisError}</p>
              ) : null}
              {analysis?.meta?.warnings?.length ? (
                <div className="space-y-1 text-xs text-amber-300">
                  {analysis.meta.warnings.map((warn) => (
                    <p key={warn}>{warn}</p>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="rounded-xl border border-slate-700 p-4 space-y-3">
              <p className="text-xs font-semibold text-slate-200">
                Analysis Summary
              </p>
              {analysis ? (
                <div className="space-y-3 text-xs text-slate-300">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-slate-400">Replay Points</p>
                      <p className="text-slate-100">
                        {analysis.point_count}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400">Window</p>
                      <p className="text-slate-100">
                        {(analysis.window_sec / 60).toFixed(0)} min
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400">Loiter</p>
                      <p className="text-slate-100">
                        {analysis.loiter.detected ? "Detected" : "None"}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400">Geofence Events</p>
                      <p className="text-slate-100">
                        {analysis.geofences.events.length}
                      </p>
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800 p-3">
                    <p className="text-[11px] text-slate-400">Loiter Detail</p>
                    <p className="text-slate-100">
                      Center:{" "}
                      {analysis.loiter.center
                        ? `${analysis.loiter.center.lat.toFixed(2)}, ${analysis.loiter.center.lon.toFixed(2)}`
                        : "-"}
                    </p>
                    <p className="text-slate-100">
                      Max Distance:{" "}
                      {analysis.loiter.max_distance_km !== undefined
                        ? `${analysis.loiter.max_distance_km.toFixed(2)} km`
                        : "-"}
                    </p>
                    <p className="text-slate-100">
                      Duration:{" "}
                      {analysis.loiter.duration_sec
                        ? `${(analysis.loiter.duration_sec / 60).toFixed(1)} min`
                        : "-"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-800 p-3 space-y-2">
                    <p className="text-[11px] text-slate-400">Geofence Log</p>
                    {analysis.geofences.events.length ? (
                      analysis.geofences.events.slice(-6).map((event, idx) => (
                        <div
                          key={`${event.ts}-${idx}`}
                          className="flex justify-between text-[11px]"
                        >
                          <span>
                            {event.geofence_label} • {event.event.toUpperCase()}
                          </span>
                          <span>
                            {new Date(event.ts * 1000).toLocaleTimeString()}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500">
                        No geofence transitions yet.
                      </p>
                    )}
                  </div>
                  <div className="rounded-lg border border-slate-800 p-3 space-y-2">
                    <p className="text-[11px] text-slate-400">Replay Trail</p>
                    {analysis.replay.length ? (
                      analysis.replay.slice(-6).map((point) => (
                        <div key={point.ts} className="flex justify-between">
                          <span>
                            {new Date(point.ts * 1000).toLocaleTimeString()}
                          </span>
                          <span>
                            {point.lat.toFixed(2)}, {point.lon.toFixed(2)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <p className="text-xs text-slate-500">
                        No replay history loaded.
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-slate-500">
                  Select a tracker to view analysis details.
                </p>
              )}
            </div>
          </div>
        </Collapsible>

        <Collapsible
          title="Live Tracker Feed"
          meta={data ? `${data.count} live signals` : "Loading"}
          open={feedOpen}
          onToggle={() => setFeedOpen((prev) => !prev)}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div>
                <label htmlFor="tracker-mode" className="text-xs text-slate-300">
                  Mode
                </label>
                <select
                  id="tracker-mode"
                  name="tracker-mode"
                  value={mode}
                  onChange={(event) => setMode(event.target.value as typeof mode)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                >
                  <option value="combined">Combined</option>
                  <option value="flights">Flights</option>
                  <option value="ships">Ships</option>
                </select>
              </div>
              <div>
                <label htmlFor="tracker-category" className="text-xs text-slate-300">
                  Category
                </label>
                <select
                  id="tracker-category"
                  name="tracker-category"
                  value={categoryFilter}
                  onChange={(event) => setCategoryFilter(event.target.value)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                >
                  {categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setIncludeCommercial((prev) => !prev)}
                  className={`rounded-xl border px-3 py-2 text-xs ${
                    includeCommercial
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  }`}
                >
                  Commercial {includeCommercial ? "On" : "Off"}
                </button>
                <button
                  type="button"
                  onClick={() => setIncludePrivate((prev) => !prev)}
                  className={`rounded-xl border px-3 py-2 text-xs ${
                    includePrivate
                      ? "border-green-400/70 text-green-200"
                      : "border-slate-700 text-slate-300"
                  }`}
                >
                  Private {includePrivate ? "On" : "Off"}
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <div>
                <label htmlFor="tracker-country" className="text-xs text-slate-300">
                  Country
                </label>
                <input
                  id="tracker-country"
                  name="tracker-country"
                  value={countryFilter}
                  onChange={(event) => setCountryFilter(event.target.value)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  placeholder="United States"
                />
              </div>
              <div>
                <label htmlFor="tracker-operator" className="text-xs text-slate-300">
                  Operator
                </label>
                <input
                  id="tracker-operator"
                  name="tracker-operator"
                  value={operatorFilter}
                  onChange={(event) => setOperatorFilter(event.target.value)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  placeholder="AAL / American"
                />
              </div>
              <div>
                <label htmlFor="tracker-id" className="text-xs text-slate-300">
                  Identifier
                </label>
                <input
                  id="tracker-id"
                  name="tracker-id"
                  value={idFilter}
                  onChange={(event) => setIdFilter(event.target.value)}
                  className="mt-1 w-full rounded-xl bg-slate-950/60 border border-slate-700 px-3 py-2 text-sm text-slate-100"
                  placeholder="Flight / tail / ICAO24"
                />
              </div>
            </div>
            <label htmlFor="tracker-search" className="sr-only">
              Search trackers
            </label>
            <input
              id="tracker-search"
              name="tracker-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="w-full rounded-xl bg-slate-950/60 border border-slate-700 px-4 py-2 text-sm text-slate-100"
              placeholder="Search flight number, operator, tail, ICAO24..."
            />
            {query.trim().length > 1 && (
              <div className="rounded-xl border border-slate-700 p-4 space-y-4">
                <p className="text-xs text-slate-300 mb-2">
                  Search Results {filteredSearchResults ? `(${filteredSearchResults.count})` : "(...)"}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {(filteredSearchResults?.points || []).map((point) => (
                    <button
                      key={point.id}
                      onClick={() => setSelectedId(point.id)}
                      className="rounded-lg border border-slate-700 p-3 text-left hover:border-green-400/40"
                    >
                      <p className="text-slate-100 font-medium">{point.label}</p>
                      <p className="text-xs text-slate-300">
                        {point.kind.toUpperCase()} • {point.category} • {point.operator_name || point.operator || "-"}
                      </p>
                    </button>
                  ))}
                </div>
                {history && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <div className="text-xs text-slate-300 space-y-2">
                      <p>History points: {history.summary?.points ?? history.history.length}</p>
                      {history.summary?.distance_km ? (
                        <p>Route distance: {history.summary.distance_km.toFixed(2)} km</p>
                      ) : null}
                      {history.summary?.direction ? (
                        <p>
                          Direction: {history.summary.direction}{" "}
                          {history.summary.bearing_deg !== undefined ? `(${history.summary.bearing_deg.toFixed(1)}°)` : ""}
                        </p>
                      ) : null}
                      {history.summary?.avg_speed_kts ? (
                        <p>Avg speed: {history.summary.avg_speed_kts.toFixed(1)} kts</p>
                      ) : null}
                      {history.summary?.avg_altitude_ft ? (
                        <p>Avg altitude: {history.summary.avg_altitude_ft.toFixed(0)} ft</p>
                      ) : null}
                      {history.summary?.duration_sec ? (
                        <p>Duration: {(history.summary.duration_sec / 60).toFixed(1)} min</p>
                      ) : null}
                      {history.summary?.route_hint ? <p>Route: {history.summary.route_hint}</p> : null}
                    </div>
                    <div className="text-xs text-slate-300 space-y-2">
                      {detail?.point && (
                        <div className="rounded-lg border border-slate-700 p-3 text-xs text-slate-100 space-y-1">
                          <p className="text-slate-100 font-medium">{detail.point.label}</p>
                          <p>{detail.point.operator_name || detail.point.operator || "-"} {detail.point.flight_number || ""}</p>
                          <p>ICAO24: {detail.point.icao24 || "-"}</p>
                          <p>Tail: {detail.point.tail_number || "-"}</p>
                          <p>Country: {detail.point.country || "-"}</p>
                          <p>
                            Alt: {detail.point.altitude_ft ? `${detail.point.altitude_ft.toFixed(0)} ft` : "-"} | Spd:{" "}
                            {detail.point.speed_kts ? `${detail.point.speed_kts.toFixed(0)} kts` : "-"}
                          </p>
                        </div>
                      )}
                      <div className="max-h-48 overflow-y-auto pr-2 space-y-1">
                        {history.history.slice(-12).map((point) => (
                          <div key={point.ts} className="flex justify-between">
                            <span>{new Date(point.ts * 1000).toLocaleTimeString()}</span>
                            <span>
                              {point.lat.toFixed(2)}, {point.lon.toFixed(2)}{" "}
                              {point.speed_kts ? `${point.speed_kts.toFixed(0)} kts` : ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {filteredPoints.slice(0, 12).map((point) => (
                <div key={`${point.kind}-${point.label}`} className="rounded-xl border border-slate-700 p-4">
                  <p className="text-slate-100 font-medium">{point.label}</p>
                  <p className="text-xs text-slate-300">
                    {point.kind.toUpperCase()} • {point.category} • {point.country || "unknown"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </Collapsible>
      </div>
    </Card>
  );
}

export default function Trackers() {
  return <TrackersPanel />;
}
