import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Map as MapInstance, GeoJSONSource, StyleSpecification } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { loadMapLibre } from "../../lib/maplibre";
import type { GlobeGeographyData } from "../../lib/globeGeography";
import { AREA_STORAGE_KEY, BLUE_MARBLE_TILES, areaCollection, coordinateBounds, normalizeLongitude, observationCollection, readAreas, type MapObservation, type ResearchArea } from "../../lib/worldMap";

type Props = {
  geography: GlobeGeographyData | null;
  observations: MapObservation[];
  focus: { lat?: number | null; lon?: number | null } | null;
  cameraPreset: "overview" | "focus" | "free";
  reducedMotion: boolean;
  onSelect: (id: string) => void;
  toolsHost: HTMLElement | null;
};

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };
const STYLE: StyleSpecification = {
  version: 8,
  projection: { type: "globe" },
  sources: {
    land: { type: "geojson", data: EMPTY, attribution: 'Context: <a href="https://www.naturalearthdata.com/about/terms-of-use/">Natural Earth</a> · de facto boundaries' },
    borders: { type: "geojson", data: EMPTY },
    imagery: { type: "raster", tiles: [BLUE_MARBLE_TILES], tileSize: 256, maxzoom: 8, attribution: 'Historical Blue Marble composite: <a href="https://www.earthdata.nasa.gov/data/tools/gibs">NASA EOSDIS GIBS</a>' },
    observations: { type: "geojson", data: EMPTY },
    areas: { type: "geojson", data: EMPTY },
  },
  layers: [
    { id: "ocean", type: "background", paint: { "background-color": "#102838" } },
    { id: "land", type: "fill", source: "land", paint: { "fill-color": "#244842" } },
    { id: "imagery", type: "raster", source: "imagery", paint: { "raster-fade-duration": 0 } },
    { id: "borders", type: "line", source: "borders", paint: { "line-color": "#dfecd9", "line-opacity": 0.55, "line-width": 0.75 } },
    { id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": "#ffd38a", "fill-opacity": 0.12 } },
    { id: "areas-edge", type: "line", source: "areas", paint: { "line-color": "#ffd38a", "line-width": 2, "line-dasharray": [3, 2] } },
    { id: "trails", type: "line", source: "observations", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["get", "color"], "line-width": 1.5, "line-opacity": 0.7 } },
    { id: "points", type: "circle", source: "observations", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": ["get", "color"], "circle-radius": ["case", ["==", ["get", "kind"], "pulse"], 7, 4], "circle-stroke-width": 1.5, "circle-stroke-color": "#07141d", "circle-opacity": 0.9 } },
  ],
};

export function WorldMapCanvas({ geography, observations, focus, cameraPreset, reducedMotion, onSelect, toolsHost }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapInstance | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tileError, setTileError] = useState(false);
  const [imagery, setImagery] = useState(true);
  const [projection, setProjection] = useState<"globe" | "mercator">("globe");
  const [coordinates, setCoordinates] = useState("0.000°, 0.000°");
  const [query, setQuery] = useState("");
  const [areaName, setAreaName] = useState("");
  const [areas, setAreas] = useState<ResearchArea[]>([]);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [areaStorageValid, setAreaStorageValid] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);

  useEffect(() => {
    try { setAreas(readAreas(localStorage.getItem(AREA_STORAGE_KEY))); }
    catch (failure) { setAreaStorageValid(false); setAreaError(failure instanceof Error ? failure.message : "Saved areas unavailable."); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let map: MapInstance | null = null;
    let resize: ResizeObserver | null = null;
    loadMapLibre().then(lib => {
      if (cancelled || !container.current) return;
      const instance: MapInstance = new lib.Map({ container: container.current, style: STYLE, center: [0, 20], zoom: 1.2, maxZoom: 12, renderWorldCopies: false, attributionControl: false, canvasContextAttributes: { antialias: true } });
      map = instance;
      mapRef.current = instance;
      map.addControl(new lib.AttributionControl({ compact: false }), "bottom-right");
      map.addControl(new lib.NavigationControl({ visualizePitch: true }), "bottom-right");
      map.addControl(new lib.ScaleControl({ unit: "metric" }), "bottom-left");
      // Controls and local geometry need a ready style, not every remote tile.
      // Tile availability is reported independently below.
      map.on("style.load", () => {
        if (cancelled) return;
        setReady(true);
        const center = instance.getCenter();
        setCoordinates(`${center.lat.toFixed(3)}°, ${normalizeLongitude(center.lng).toFixed(3)}°`);
      });
      map.on("error", event => {
        if (cancelled) return;
        if ((event as { sourceId?: string }).sourceId === "imagery" || event.error?.message?.includes("gibs.earthdata.nasa.gov")) setTileError(true);
        else setError(event.error?.message || "Map rendering unavailable.");
      });
      map.on("moveend", () => { const center = map!.getCenter(); setCoordinates(`${center.lat.toFixed(3)}°, ${normalizeLongitude(center.lng).toFixed(3)}°`); });
      map.on("click", "points", event => { const id = event.features?.[0]?.properties?.observationId; if (typeof id === "string") selectRef.current(id); });
      map.on("mouseenter", "points", () => { map!.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "points", () => { map!.getCanvas().style.cursor = ""; });
      map.getCanvas().setAttribute("aria-label", "World map. Arrow keys pan; plus and minus zoom. Use Map tools to search and select research areas.");
      resize = new ResizeObserver(() => map?.resize());
      resize.observe(container.current);
    }).catch(failure => { if (!cancelled) setError(failure instanceof Error ? failure.message : "Map unavailable."); });
    return () => { cancelled = true; resize?.disconnect(); map?.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    if (!ready || !mapRef.current || !geography) return;
    (mapRef.current.getSource("land") as GeoJSONSource).setData({ type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: geography.land_polygons } }] });
    (mapRef.current.getSource("borders") as GeoJSONSource).setData({ type: "FeatureCollection", features: (geography.country_features || []).map(country => ({ type: "Feature", properties: { name: country.name }, geometry: { type: "MultiLineString", coordinates: country.rings } })) });
  }, [ready, geography]);
  useEffect(() => { if (ready) (mapRef.current?.getSource("observations") as GeoJSONSource)?.setData(observationCollection(observations)); }, [ready, observations]);
  useEffect(() => { if (ready) (mapRef.current?.getSource("areas") as GeoJSONSource)?.setData(areaCollection(areas)); }, [ready, areas]);
  useEffect(() => { if (ready) mapRef.current?.setLayoutProperty("imagery", "visibility", imagery ? "visible" : "none"); }, [ready, imagery]);
  useEffect(() => { if (ready) mapRef.current?.setProjection({ type: projection }); }, [ready, projection]);
  useEffect(() => {
    if (!ready) return;
    const duration = reducedMotion ? 0 : 600;
    if (cameraPreset === "overview") mapRef.current?.easeTo({ center: [0, 20], zoom: 1.2, pitch: 0, bearing: 0, duration });
    else if (cameraPreset === "focus" && typeof focus?.lon === "number" && typeof focus.lat === "number") mapRef.current?.easeTo({ center: [focus.lon, focus.lat], zoom: Math.max(mapRef.current.getZoom(), 4), duration });
  }, [ready, cameraPreset, focus?.lat, focus?.lon, reducedMotion]);

  const countries = useMemo(() => !query.trim() ? [] : (geography?.country_features || []).filter(country => country.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 8), [query, geography]);
  function fit(bounds: ResearchArea["bounds"]) {
    const [west, south, east, north] = bounds;
    mapRef.current?.fitBounds([[west, south], [east < west ? east + 360 : east, north]], { padding: 100, maxZoom: 8, duration: reducedMotion ? 0 : 600 });
  }
  function saveArea() {
    if (!mapRef.current || !areaName.trim() || !areaStorageValid) return;
    try {
      const existing = readAreas(localStorage.getItem(AREA_STORAGE_KEY));
      if (existing.length >= 20) throw new Error("Maximum 20 saved research areas in this browser.");
      const bounds = mapRef.current.getBounds();
      const width = bounds.getEast() - bounds.getWest();
      if (width >= 360) throw new Error("Zoom in before saving an area of interest.");
      const area: ResearchArea = { id: crypto.randomUUID(), name: areaName.trim(), bounds: [normalizeLongitude(bounds.getWest()), bounds.getSouth(), normalizeLongitude(bounds.getEast()), bounds.getNorth()], basis: "operator-viewport", createdAt: new Date().toISOString() };
      const next = readAreas(JSON.stringify([...existing, area]));
      localStorage.setItem(AREA_STORAGE_KEY, JSON.stringify(next));
      setAreas(next); setAreaName(""); setAreaError(null);
    } catch (failure) { setAreaError(failure instanceof Error ? failure.message : "Could not save research area."); }
  }

  function removeArea(id: string) {
    try {
      const next = readAreas(localStorage.getItem(AREA_STORAGE_KEY)).filter(area => area.id !== id);
      localStorage.setItem(AREA_STORAGE_KEY, JSON.stringify(next));
      setAreas(next); setAreaError(null);
    } catch (failure) { setAreaError(failure instanceof Error ? failure.message : "Could not remove research area."); }
  }

  return <>
    <div ref={container} className="world-map-canvas" data-testid="world-map-canvas" />
    {toolsHost && createPortal(<section className="world-map-tools" aria-label="World map tools">
      <button type="button" className="globe-action-button" aria-expanded={toolsOpen} onClick={() => setToolsOpen(value => !value)}>Map tools</button>
      {toolsOpen && <div className="world-map-tools__body">
        <label>Projection<select aria-label="Map projection" value={projection} onChange={event => setProjection(event.target.value as typeof projection)}><option value="globe">Globe</option><option value="mercator">Flat map</option></select></label>
        <button type="button" disabled={!ready} onClick={() => mapRef.current?.easeTo({ center: [0, 20], zoom: 1.2, pitch: 0, bearing: 0, duration: reducedMotion ? 0 : 600 })}>Reset map view</button>
        <label><input type="checkbox" checked={imagery} onChange={event => setImagery(event.target.checked)} /> Historical satellite basemap</label>
        <p>NASA Blue Marble composite; not live imagery or street-level detail. Raster coverage ends at ±85.05°. Borders are de facto context, not legal boundaries.</p>
        <label>Find country<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Country name" /></label>
        {countries.map(country => <button type="button" key={country.id} onClick={() => {
          fit(coordinateBounds(country.rings.flat()));
        }}>{country.name}</button>)}
        {query.trim() && !countries.length && <p>No matching country in the reviewed context.</p>}
        <label>Research area name<input value={areaName} maxLength={80} onChange={event => setAreaName(event.target.value)} /></label>
        <button type="button" disabled={!ready || !areaName.trim() || !areaStorageValid} onClick={saveArea}>Save current map area</button>
        <p>Areas are operator-defined viewport bounds, not event extents. Saved only in this browser.</p>
        {areas.map(area => <div key={area.id} className="flex gap-2"><button type="button" className="flex-1" onClick={() => fit(area.bounds)}>{area.name}</button><button type="button" aria-label={`Remove ${area.name}`} disabled={!areaStorageValid} onClick={() => removeArea(area.id)}>Remove</button></div>)}
        {areaError && <p role="alert">{areaError}</p>}
      </div>}
      <output aria-label="Map center coordinates">{coordinates}</output>
      {(!ready && !error) && <p role="status">Loading map engine…</p>}
      {error && <p role="alert">Map unavailable: {error}. The source-backed Browse list remains available.</p>}
      {tileError && imagery && <p role="status">Some imagery tiles are unavailable. Reviewed vector geography remains visible; satellite coverage may be incomplete.</p>}
    </section>, toolsHost)}
  </>;
}
