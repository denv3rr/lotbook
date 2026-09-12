import type { FeatureCollection, Geometry, Polygon, MultiPolygon } from "geojson";

export type MapObservation = { id: string; geometry: Geometry; color: string; kind: "point" | "path" | "pulse" };
export type ResearchArea = { id: string; name: string; bounds: [number, number, number, number]; createdAt: string; basis: "operator-viewport" };
export const AREA_STORAGE_KEY = "lotbook_world_research_areas_v1";
export const LEGACY_AREA_STORAGE_KEY = "clear_world_research_areas_v1";

export function readAreaStorageRaw(): string | null {
  try {
    return localStorage.getItem(AREA_STORAGE_KEY) ?? localStorage.getItem(LEGACY_AREA_STORAGE_KEY);
  } catch {
    return null;
  }
}
export const BLUE_MARBLE_TILES = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
export const ESRI_WORLD_IMAGERY_TILES = "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
export const OSM_RASTER_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const MAX_MAP_ZOOM = 19;
export const DETAIL_MIN_ZOOM = 0;
export const GLOBE_FLAT_SATELLITE_ZOOM = 12;
export type BasemapMode = "satellite" | "street";

export function basemapSourceLabel(zoom: number, mode: BasemapMode): string {
  if (mode === "street") return "OpenStreetMap";
  return zoom < 8 ? "NASA Blue Marble under Esri satellite" : "Esri World Imagery";
}

export function projectionForZoom(preferred: "globe" | "mercator", zoom: number): "globe" | "mercator" {
  if (preferred === "mercator") return "mercator";
  return zoom >= GLOBE_FLAT_SATELLITE_ZOOM ? "mercator" : "globe";
}

export type SceneCameraDefaults = { target_lat?: number; target_lon?: number; distance?: number; pitch?: number; bearing?: number };
export type SceneBounds = { min_lon?: number; min_lat?: number; max_lon?: number; max_lat?: number };
export function sceneCameraTarget(defaults?: SceneCameraDefaults): [number, number] | null {
  const lat = defaults?.target_lat; const lon = defaults?.target_lon;
  return typeof lat === "number" && Number.isFinite(lat) && Math.abs(lat) <= 90 && typeof lon === "number" && Number.isFinite(lon) && Math.abs(lon) <= 180 ? [lon, lat] : null;
}
export function isImageryError(event: { sourceId?: unknown }): boolean {
  // Source identity is attached by MapLibre; arbitrary error text is not a URL.
  return event.sourceId === "imagery" || event.sourceId === "detail" || event.sourceId === "street";
}

export function centeredMercatorZoom(center: [number, number], width: number, height: number): number {
  // MapLibre's zoom-zero world is 512 CSS pixels. With no world copies, each
  // half-viewport must fit between the requested center and the nearest edge.
  // Mercator y = (1 - ln(tan(pi/4 + latitude/2)) / pi) / 2.
  const latitude = Math.max(-85.05112878, Math.min(85.05112878, center[1]));
  const x = (center[0] + 180) / 360;
  const y = (1 - Math.log(Math.tan(Math.PI / 4 + latitude * Math.PI / 360)) / Math.PI) / 2;
  const scale = Math.max(width / (1024 * Math.max(0, Math.min(x, 1 - x))), height / (1024 * Math.max(0, Math.min(y, 1 - y))));
  // At projection edges an exact center is impossible; retain the map's limit.
  return Math.max(0, Math.min(MAX_MAP_ZOOM, Math.log2(scale)));
}

export function normalizeLongitude(value: number): number {
  return ((value + 180) % 360 + 360) % 360 - 180;
}

export function validateBounds(value: unknown): value is ResearchArea["bounds"] {
  if (!Array.isArray(value) || value.length !== 4 || !value.every(item => typeof item === "number" && Number.isFinite(item))) return false;
  const [west, south, east, north] = value;
  return west >= -180 && west <= 180 && east >= -180 && east <= 180 && west !== east && south >= -90 && north <= 90 && south < north;
}

export function coordinateBounds(points: number[][]): ResearchArea["bounds"] {
  if (!points.length || points.some(point => point.length < 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1]) || point[1] < -90 || point[1] > 90)) throw new Error("Invalid geographic coordinates.");
  const longitude = [...new Set(points.map(point => normalizeLongitude(point[0])))].sort((a, b) => a - b);
  let gap = -1; let afterGap = 0;
  longitude.forEach((value, index) => {
    const next = index + 1 < longitude.length ? longitude[index + 1] : longitude[0] + 360;
    if (next - value > gap) { gap = next - value; afterGap = (index + 1) % longitude.length; }
  });
  const latitude = points.map(point => point[1]);
  return [longitude[afterGap], Math.min(...latitude), longitude[(afterGap + longitude.length - 1) % longitude.length], Math.max(...latitude)];
}

export function areaGeometry(bounds: ResearchArea["bounds"]): Polygon | MultiPolygon {
  if (!validateBounds(bounds)) throw new Error("Invalid research-area bounds.");
  const [west, south, east, north] = bounds;
  const ring = (left: number, right: number) => [[left, south], [right, south], [right, north], [left, north], [left, south]];
  return west < east
    ? { type: "Polygon", coordinates: [ring(west, east)] }
    : { type: "MultiPolygon", coordinates: [[ring(west, 180)], [ring(-180, east)]] };
}

export function readAreas(raw: string | null): ResearchArea[] {
  if (!raw) return [];
  const areas: unknown = JSON.parse(raw);
  if (!Array.isArray(areas) || areas.length > 20 || areas.some(area => !area || typeof area.id !== "string" || typeof area.name !== "string" || !area.name.trim() || area.name.length > 80 || area.basis !== "operator-viewport" || !validateBounds(area.bounds) || typeof area.createdAt !== "string" || !Number.isFinite(Date.parse(area.createdAt)))) throw new Error("Saved research areas are invalid; existing browser data was left unchanged.");
  if (new Set(areas.map(area => area.id)).size !== areas.length) throw new Error("Saved research area identifiers are duplicated.");
  return areas;
}

export function observationCollection(observations: MapObservation[]): FeatureCollection {
  return { type: "FeatureCollection", features: observations.map(item => ({ type: "Feature", id: item.id, geometry: item.geometry, properties: { observationId: item.id, color: item.color, kind: item.kind } })) };
}

export function areaCollection(areas: ResearchArea[]): FeatureCollection {
  return { type: "FeatureCollection", features: areas.map(area => ({ type: "Feature", id: area.id, geometry: areaGeometry(area.bounds), properties: { name: area.name, basis: area.basis, createdAt: area.createdAt } })) };
}
