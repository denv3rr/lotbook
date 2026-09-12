export type MapLibre = typeof import("maplibre-gl");

import mapLibreCssUrl from "maplibre-gl/dist/maplibre-gl.css?url";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

export const mapLibreWorkerUrl = workerUrl;

let cached: MapLibre | null = null;

function ensureMapLibreStylesheet() {
  if (typeof document === "undefined") return;
  if (document.querySelector("link[data-lotbook-maplibre-css]")) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = mapLibreCssUrl;
  link.dataset.lotbookMaplibreCss = "true";
  document.head.appendChild(link);
}

export async function loadMapLibre(): Promise<MapLibre> {
  if (cached) return cached;
  ensureMapLibreStylesheet();
  const maplibre = await import("maplibre-gl");
  maplibre.setWorkerUrl(workerUrl);
  cached = maplibre;
  return maplibre;
}
