import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

const SCENE_STATE_KEY = "lotbook_scene_state";
const LEGACY_SCENE_STATE_KEY = "clear_scene_state";
const SCENE_STATE_VERSION = 2;

export type SceneId = "trackers" | "intel" | "overview";
export type TrackerSceneMode = "combined" | "flights" | "ships";
export type IntelSceneLens = "combined" | "weather" | "conflict" | "news" | "emotion";
export type SceneCameraPreset = "overview" | "focus" | "free";
export type SceneOverlayKey =
  | "detailsVisible"
  | "showIntelHotspots"
  | "showIntelRegions"
  | "showTrackerPoints"
  | "showTrackerTrails";

export type SceneRuntimeState = {
  cameraPreset: SceneCameraPreset;
  detailsVisible: boolean;
  intelCategories: string[];
  intelIndustry: string;
  intelLens: IntelSceneLens;
  intelSources: string[];
  showIntelHotspots: boolean;
  showIntelRegions: boolean;
  showTrackerPoints: boolean;
  showTrackerTrails: boolean;
  trackerCategory: string;
  trackerCountry: string;
  trackerMode: TrackerSceneMode;
  trackerOperator: string;
};

export type SceneDefinition = {
  id: SceneId;
  label: string;
  description: string;
  buildPath: (state: SceneRuntimeState) => string;
  fallbackStrategy?: "none" | "trackerSnapshot";
};

type SceneContextValue = {
  activeScene: SceneDefinition | null;
  activeScenePath: string | null;
  clearIntelFilters: () => void;
  clearTrackerFilters: () => void;
  closeScene: () => void;
  isOpen: boolean;
  openScene: (sceneId?: SceneId) => void;
  sceneState: SceneRuntimeState;
  setCameraPreset: (preset: SceneCameraPreset) => void;
  setIntelIndustry: (industry: string) => void;
  setIntelLens: (lens: IntelSceneLens) => void;
  setOverlayVisibility: (key: SceneOverlayKey, visible: boolean) => void;
  resetOverlayVisibility: () => void;
  setTrackerCategory: (category: string) => void;
  setTrackerCountry: (country: string) => void;
  setTrackerMode: (mode: TrackerSceneMode) => void;
  setTrackerOperator: (operator: string) => void;
  toggleIntelCategory: (category: string) => void;
  toggleIntelSource: (source: string) => void;
  toggleScene: (sceneId?: SceneId) => void;
};

const DEFAULT_SCENE_STATE: SceneRuntimeState = {
  cameraPreset: "free",
  detailsVisible: false,
  intelCategories: [],
  intelIndustry: "all",
  intelLens: "combined",
  intelSources: [],
  showIntelHotspots: true,
  showIntelRegions: true,
  showTrackerPoints: true,
  showTrackerTrails: true,
  trackerCategory: "all",
  trackerCountry: "",
  trackerMode: "combined",
  trackerOperator: "",
};

function appendQueryParam(params: URLSearchParams, key: string, value: string) {
  if (!value.trim()) return;
  params.set(key, value.trim());
}

const SCENES: Record<SceneId, SceneDefinition> = {
  overview: {
    id: "overview",
    label: "World",
    description: "Trackers and regional signals.",
    buildPath: (state) => {
      const params = new URLSearchParams();
      params.set("mode", state.trackerMode);
      if (state.trackerCategory !== "all") {
        params.set("category", state.trackerCategory);
      }
      appendQueryParam(params, "country", state.trackerCountry);
      appendQueryParam(params, "operator", state.trackerOperator);
      params.set("industry", state.intelIndustry);
      if (state.intelCategories.length) {
        params.set("categories", state.intelCategories.join(","));
      }
      if (state.intelSources.length) {
        params.set("sources", state.intelSources.join(","));
      }
      return `/api/osint/scene/overview?${params.toString()}`;
    },
    fallbackStrategy: "trackerSnapshot",
  },
  trackers: {
    id: "trackers",
    label: "Trackers",
    description: "Live positions and trails.",
    buildPath: (state) => {
      const params = new URLSearchParams();
      params.set("mode", state.trackerMode);
      if (state.trackerCategory !== "all") {
        params.set("category", state.trackerCategory);
      }
      appendQueryParam(params, "country", state.trackerCountry);
      appendQueryParam(params, "operator", state.trackerOperator);
      return `/api/osint/scene/trackers?${params.toString()}`;
    },
    fallbackStrategy: "trackerSnapshot",
  },
  intel: {
    id: "intel",
    label: "Signals",
    description: "Regional weather, conflict, news, and emotion.",
    buildPath: (state) => {
      const params = new URLSearchParams();
      params.set("industry", state.intelIndustry);
      if (state.intelCategories.length) {
        params.set("categories", state.intelCategories.join(","));
      }
      if (state.intelSources.length) {
        params.set("sources", state.intelSources.join(","));
      }
      return `/api/osint/scene/intel?${params.toString()}`;
    },
    fallbackStrategy: "none",
  },
};

function normalizeStringArray(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((entry): entry is string => typeof entry === "string")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizeBoolean(value: unknown, fallback: boolean) {
  if (typeof value === "boolean") return value;
  return fallback;
}

function readStoredSceneState(): SceneRuntimeState {
  if (typeof window === "undefined") return DEFAULT_SCENE_STATE;
  try {
    const raw = window.localStorage.getItem(SCENE_STATE_KEY) ?? window.localStorage.getItem(LEGACY_SCENE_STATE_KEY);
    if (!raw) return DEFAULT_SCENE_STATE;
    const parsed = JSON.parse(raw) as Partial<SceneRuntimeState> & { version?: number };
    const currentVersion = parsed.version === SCENE_STATE_VERSION;
    return {
      trackerMode:
        parsed.trackerMode === "flights" ||
        parsed.trackerMode === "ships" ||
        parsed.trackerMode === "combined"
          ? parsed.trackerMode
          : DEFAULT_SCENE_STATE.trackerMode,
      intelLens:
        parsed.intelLens === "weather" ||
        parsed.intelLens === "conflict" ||
        parsed.intelLens === "news" ||
        parsed.intelLens === "emotion" ||
        parsed.intelLens === "combined"
          ? parsed.intelLens
          : DEFAULT_SCENE_STATE.intelLens,
      cameraPreset:
        parsed.cameraPreset === "overview" ||
        parsed.cameraPreset === "focus" ||
        parsed.cameraPreset === "free"
          ? parsed.cameraPreset
          : DEFAULT_SCENE_STATE.cameraPreset,
      detailsVisible: normalizeBoolean(
        currentVersion ? parsed.detailsVisible : undefined,
        DEFAULT_SCENE_STATE.detailsVisible,
      ),
      trackerCategory:
        currentVersion && typeof parsed.trackerCategory === "string" && parsed.trackerCategory.trim()
          ? parsed.trackerCategory.trim()
          : DEFAULT_SCENE_STATE.trackerCategory,
      trackerCountry:
        currentVersion && typeof parsed.trackerCountry === "string"
          ? parsed.trackerCountry.trim()
          : DEFAULT_SCENE_STATE.trackerCountry,
      trackerOperator:
        currentVersion && typeof parsed.trackerOperator === "string"
          ? parsed.trackerOperator.trim()
          : DEFAULT_SCENE_STATE.trackerOperator,
      intelIndustry:
        currentVersion && typeof parsed.intelIndustry === "string" && parsed.intelIndustry.trim()
          ? parsed.intelIndustry.trim()
          : DEFAULT_SCENE_STATE.intelIndustry,
      intelCategories: currentVersion
        ? normalizeStringArray(parsed.intelCategories)
        : DEFAULT_SCENE_STATE.intelCategories,
      intelSources: currentVersion
        ? normalizeStringArray(parsed.intelSources)
        : DEFAULT_SCENE_STATE.intelSources,
      showIntelHotspots: normalizeBoolean(
        currentVersion ? parsed.showIntelHotspots : undefined,
        DEFAULT_SCENE_STATE.showIntelHotspots,
      ),
      showIntelRegions: normalizeBoolean(
        currentVersion ? parsed.showIntelRegions : undefined,
        DEFAULT_SCENE_STATE.showIntelRegions,
      ),
      showTrackerPoints: normalizeBoolean(
        currentVersion ? parsed.showTrackerPoints : undefined,
        DEFAULT_SCENE_STATE.showTrackerPoints,
      ),
      showTrackerTrails: normalizeBoolean(
        currentVersion ? parsed.showTrackerTrails : undefined,
        DEFAULT_SCENE_STATE.showTrackerTrails,
      ),
    };
  } catch {
    return DEFAULT_SCENE_STATE;
  }
}

const SceneContext = createContext<SceneContextValue | null>(null);

export function SceneProvider({ children }: { children: ReactNode }) {
  const [activeScene, setActiveScene] = useState<SceneDefinition | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [sceneState, setSceneState] = useState<SceneRuntimeState>(readStoredSceneState);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        SCENE_STATE_KEY,
        JSON.stringify({ ...sceneState, version: SCENE_STATE_VERSION }),
      );
      window.localStorage.removeItem(LEGACY_SCENE_STATE_KEY);
    } catch {
      // Ignore storage failures and keep runtime-only state.
    }
  }, [sceneState]);

  const openScene = useCallback((sceneId?: SceneId) => {
    const nextSceneId = sceneId || activeScene?.id || "overview";
    startTransition(() => {
      setActiveScene(SCENES[nextSceneId]);
      setIsOpen(true);
    });
  }, [activeScene?.id]);

  const closeScene = useCallback(() => {
    startTransition(() => {
      setIsOpen(false);
    });
  }, []);

  const toggleScene = useCallback(
    (sceneId?: SceneId) => {
      const nextSceneId = sceneId || activeScene?.id || "overview";
      if (isOpen && activeScene?.id === nextSceneId) {
        closeScene();
        return;
      }
      openScene(nextSceneId);
    },
    [activeScene?.id, closeScene, isOpen, openScene],
  );

  const setTrackerMode = useCallback((mode: TrackerSceneMode) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, trackerMode: mode }));
    });
  }, []);

  const setTrackerCategory = useCallback((category: string) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, trackerCategory: category || "all" }));
    });
  }, []);

  const setTrackerCountry = useCallback((country: string) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, trackerCountry: country }));
    });
  }, []);

  const setTrackerOperator = useCallback((operator: string) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, trackerOperator: operator }));
    });
  }, []);

  const clearTrackerFilters = useCallback(() => {
    startTransition(() => {
      setSceneState((current) => ({
        ...current,
        trackerCategory: DEFAULT_SCENE_STATE.trackerCategory,
        trackerCountry: DEFAULT_SCENE_STATE.trackerCountry,
        trackerOperator: DEFAULT_SCENE_STATE.trackerOperator,
      }));
    });
  }, []);

  const setIntelLens = useCallback((lens: IntelSceneLens) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, intelLens: lens }));
    });
  }, []);

  const setIntelIndustry = useCallback((industry: string) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, intelIndustry: industry || "all" }));
    });
  }, []);

  const setOverlayVisibility = useCallback((key: SceneOverlayKey, visible: boolean) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, [key]: visible }));
    });
  }, []);

  const resetOverlayVisibility = useCallback(() => {
    startTransition(() => {
      setSceneState((current) => ({
        ...current,
        detailsVisible: DEFAULT_SCENE_STATE.detailsVisible,
        showIntelHotspots: DEFAULT_SCENE_STATE.showIntelHotspots,
        showIntelRegions: DEFAULT_SCENE_STATE.showIntelRegions,
        showTrackerPoints: DEFAULT_SCENE_STATE.showTrackerPoints,
        showTrackerTrails: DEFAULT_SCENE_STATE.showTrackerTrails,
      }));
    });
  }, []);

  const toggleIntelCategory = useCallback((category: string) => {
    startTransition(() => {
      setSceneState((current) => {
        const next = new Set(current.intelCategories);
        if (next.has(category)) {
          next.delete(category);
        } else {
          next.add(category);
        }
        return { ...current, intelCategories: Array.from(next) };
      });
    });
  }, []);

  const toggleIntelSource = useCallback((source: string) => {
    startTransition(() => {
      setSceneState((current) => {
        const next = new Set(current.intelSources);
        if (next.has(source)) {
          next.delete(source);
        } else {
          next.add(source);
        }
        return { ...current, intelSources: Array.from(next) };
      });
    });
  }, []);

  const clearIntelFilters = useCallback(() => {
    startTransition(() => {
      setSceneState((current) => ({
        ...current,
        intelCategories: DEFAULT_SCENE_STATE.intelCategories,
        intelIndustry: DEFAULT_SCENE_STATE.intelIndustry,
        intelSources: DEFAULT_SCENE_STATE.intelSources,
      }));
    });
  }, []);

  const setCameraPreset = useCallback((preset: SceneCameraPreset) => {
    startTransition(() => {
      setSceneState((current) => ({ ...current, cameraPreset: preset }));
    });
  }, []);

  const activeScenePath = useMemo(() => {
    if (!activeScene) return null;
    return activeScene.buildPath(sceneState);
  }, [activeScene, sceneState]);

  const value = useMemo(
    () => ({
      activeScene,
      activeScenePath,
      clearIntelFilters,
      clearTrackerFilters,
      closeScene,
      isOpen,
      openScene,
      sceneState,
      setCameraPreset,
      setIntelIndustry,
      setIntelLens,
      setOverlayVisibility,
      resetOverlayVisibility,
      setTrackerCategory,
      setTrackerCountry,
      setTrackerMode,
      setTrackerOperator,
      toggleIntelCategory,
      toggleIntelSource,
      toggleScene,
    }),
    [
      activeScene,
      activeScenePath,
      clearIntelFilters,
      clearTrackerFilters,
      closeScene,
      isOpen,
      openScene,
      sceneState,
      setCameraPreset,
      setIntelIndustry,
      setIntelLens,
      setOverlayVisibility,
      resetOverlayVisibility,
      setTrackerCategory,
      setTrackerCountry,
      setTrackerMode,
      setTrackerOperator,
      toggleIntelCategory,
      toggleIntelSource,
      toggleScene,
    ],
  );

  return <SceneContext.Provider value={value}>{children}</SceneContext.Provider>;
}

export function useSceneController() {
  const value = useContext(SceneContext);
  if (!value) {
    throw new Error("useSceneController must be used within a SceneProvider.");
  }
  return value;
}
