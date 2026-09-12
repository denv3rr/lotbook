export type LeafletLib = typeof import("leaflet");

import leafletCssUrl from "leaflet/dist/leaflet.css?url";

let cached: LeafletLib | null = null;

function ensureLeafletStylesheet() {
  if (typeof document === "undefined") return;
  if (document.querySelector("link[data-lotbook-leaflet-css]")) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = leafletCssUrl;
  link.dataset.lotbookLeafletCss = "true";
  document.head.appendChild(link);
}

export async function loadLeaflet(): Promise<LeafletLib> {
  if (cached) {
    return cached;
  }
  ensureLeafletStylesheet();
  const mod = await import("leaflet");
  const leaflet = (mod as { default?: LeafletLib }).default ?? (mod as LeafletLib);
  cached = leaflet;
  return leaflet;
}
