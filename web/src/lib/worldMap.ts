import type { FeatureCollection, Geometry, Polygon, MultiPolygon } from "geojson";

export type MapObservation = { id: string; geometry: Geometry; color: string; kind: "point" | "path" | "pulse" };
export type ResearchArea = { id: string; name: string; bounds: [number, number, number, number]; createdAt: string; basis: "operator-viewport" };
export const AREA_STORAGE_KEY = "clear_world_research_areas_v1";
export const BLUE_MARBLE_TILES = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";

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
