import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Map as MapInstance, GeoJSONSource, StyleSpecification } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { loadMapLibre } from "../../lib/maplibre";
import type { GlobeGeographyData } from "../../lib/globeGeography";
import { BLUE_MARBLE_TILES, DETAIL_MIN_ZOOM, ESRI_WORLD_IMAGERY_TILES, MAX_MAP_ZOOM, OSM_RASTER_TILES, areaCollection, centeredMercatorZoom, coordinateBounds, isImageryError, normalizeLongitude, observationCollection, sceneCameraTarget, validateBounds, type MapObservation, type ResearchArea, type SceneCameraDefaults, type SceneBounds } from "../../lib/worldMap";
import { useResearchAreas } from "../../lib/useResearchAreas";

type Props = {
  geography: GlobeGeographyData | null;
  observations: MapObservation[];
  focus: { lat?: number | null; lon?: number | null } | null;
  cameraPreset: "overview" | "focus" | "free";
  cameraDefaults?: SceneCameraDefaults;
  sceneBounds?: SceneBounds;
  sceneKey: string | null;
  cameraRevision: number;
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
    detail: { type: "raster", tiles: [ESRI_WORLD_IMAGERY_TILES], tileSize: 256, minzoom: DETAIL_MIN_ZOOM, maxzoom: MAX_MAP_ZOOM, attribution: 'Closer zoom: <a href="https://www.esri.com">Esri World Imagery</a> (Esri, Maxar, Earthstar Geographics, and the GIS User Community). Not a live satellite stream. OSM fallback: &copy; OpenStreetMap contributors' },
    observations: { type: "geojson", data: EMPTY },
    areas: { type: "geojson", data: EMPTY },
  },
  layers: [
    { id: "ocean", type: "background", paint: { "background-color": "#102838" } },
    { id: "land", type: "fill", source: "land", paint: { "fill-color": "#244842" } },
    { id: "imagery", type: "raster", source: "imagery", paint: { "raster-fade-duration": 0, "raster-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 1, 9, 0] } },
    { id: "detail", type: "raster", source: "detail", paint: { "raster-fade-duration": 0, "raster-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 0, 9, 1] } },
    { id: "borders", type: "line", source: "borders", paint: { "line-color": "#dfecd9", "line-opacity": 0.55, "line-width": 0.75 } },
    { id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": "#ffd38a", "fill-opacity": 0.12 } },
    { id: "areas-edge", type: "line", source: "areas", paint: { "line-color": "#ffd38a", "line-width": 2, "line-dasharray": [3, 2] } },
    { id: "trails", type: "line", source: "observations", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["get", "color"], "line-width": 1.5, "line-opacity": 0.7 } },
    { id: "points", type: "circle", source: "observations", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": ["get", "color"], "circle-radius": ["case", ["==", ["get", "kind"], "pulse"], 7, 4], "circle-stroke-width": 1.5, "circle-stroke-color": "#07141d", "circle-opacity": 0.9 } },
  ],
};

export function WorldMapCanvas({ geography, observations, focus, cameraPreset, cameraDefaults, sceneBounds, sceneKey, cameraRevision, reducedMotion, onSelect, toolsHost }: Props) {
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
  const vault = useResearchAreas();
  const { areas } = vault;
  const [passphrase, setPassphrase] = useState("");
  const [repeatPassphrase, setRepeatPassphrase] = useState("");
  const [areaError, setAreaError] = useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const framedScene = useRef<string | null>(null);
  const resetOverview = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const bounds = [sceneBounds?.min_lon, sceneBounds?.min_lat, sceneBounds?.max_lon, sceneBounds?.max_lat];
    // API distance describes the retired sphere camera, not a MapLibre zoom.
    // Use geographic bounds for scale, with the API target taking precedence.
    const fitted = validateBounds(bounds) ? map.cameraForBounds([[bounds[0], bounds[1]], [bounds[2] < bounds[0] ? bounds[2] + 360 : bounds[2], bounds[3]]], { padding: Math.min(80, map.getContainer().clientWidth / 5), maxZoom: 6 }) : undefined;
    const pitch = cameraDefaults?.pitch;
    const bearing = cameraDefaults?.bearing;
    const target = sceneCameraTarget(cameraDefaults);
    const minimumZoom = projection === "mercator" && target ? centeredMercatorZoom(target, map.getContainer().clientWidth, map.getContainer().clientHeight) : 0;
    map.easeTo({ center: target ?? fitted?.center ?? [0, 20], zoom: Math.max(fitted?.zoom ?? 1.2, minimumZoom), pitch: typeof pitch === "number" && Number.isFinite(pitch) ? Math.max(0, Math.min(60, pitch)) : 0, bearing: typeof bearing === "number" && Number.isFinite(bearing) ? bearing : 0, duration: reducedMotion ? 0 : 600 });
  }, [cameraDefaults?.target_lat, cameraDefaults?.target_lon, cameraDefaults?.pitch, cameraDefaults?.bearing, sceneBounds?.min_lon, sceneBounds?.min_lat, sceneBounds?.max_lon, sceneBounds?.max_lat, reducedMotion, projection]);

  useEffect(() => {
    let cancelled = false;
    let map: MapInstance | null = null;
    let resize: ResizeObserver | null = null;
    loadMapLibre().then(lib => {
      if (cancelled || !container.current) return;
      const instance: MapInstance = new lib.Map({ container: container.current, style: STYLE, center: sceneCameraTarget(cameraDefaults) ?? [0, 20], zoom: 1.2, maxZoom: MAX_MAP_ZOOM, renderWorldCopies: false, attributionControl: false, canvasContextAttributes: { antialias: true } });
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
      let detailFallback = false;
      map.on("error", event => {
        if (cancelled) return;
        if (isImageryError(event as { sourceId?: string })) {
          setTileError(true);
          const sourceId = (event as { sourceId?: string }).sourceId;
          const live = map;
          if (sourceId === "detail" && !detailFallback && live?.getSource("detail")) {
            detailFallback = true;
            if (live.getLayer("detail")) live.removeLayer("detail");
            live.removeSource("detail");
            live.addSource("detail", { type: "raster", tiles: [OSM_RASTER_TILES], tileSize: 256, minzoom: DETAIL_MIN_ZOOM, maxzoom: MAX_MAP_ZOOM, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' });
            live.addLayer({ id: "detail", type: "raster", source: "detail", paint: { "raster-fade-duration": 0, "raster-opacity": ["interpolate", ["linear"], ["zoom"], 7.5, 0, 9, 1] } }, "borders");
          }
        } else setError(event.error?.message || "Map rendering unavailable.");
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
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const visibility = imagery ? "visible" : "none";
    mapRef.current.setLayoutProperty("imagery", "visibility", visibility);
    if (mapRef.current.getLayer("detail")) mapRef.current.setLayoutProperty("detail", "visibility", visibility);
  }, [ready, imagery]);
  useEffect(() => { if (ready) mapRef.current?.setProjection({ type: projection }); }, [ready, projection]);
  useEffect(() => {
    if (!ready) return;
    const firstFrame = sceneKey !== null && framedScene.current !== sceneKey;
    if (firstFrame) framedScene.current = sceneKey;
    if (cameraPreset === "overview" || firstFrame) resetOverview();
  }, [ready, cameraPreset, cameraRevision, sceneKey, resetOverview]);
  useEffect(() => {
    if (ready && cameraPreset === "focus" && typeof focus?.lon === "number" && typeof focus.lat === "number") mapRef.current?.easeTo({ center: [focus.lon, focus.lat], zoom: Math.max(mapRef.current.getZoom(), 4), duration: reducedMotion ? 0 : 600 });
  }, [ready, cameraPreset, cameraRevision, focus?.lat, focus?.lon, reducedMotion]);

  const countries = useMemo(() => !query.trim() ? [] : (geography?.country_features || []).filter(country => country.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 8), [query, geography]);
  function fit(bounds: ResearchArea["bounds"]) {
    const [west, south, east, north] = bounds;
    mapRef.current?.fitBounds([[west, south], [east < west ? east + 360 : east, north]], { padding: 100, maxZoom: 8, duration: reducedMotion ? 0 : 600 });
  }
  async function saveArea() {
    if (!mapRef.current || !areaName.trim() || vault.state !== "unlocked" || vault.busy) return;
    try {
      const bounds = mapRef.current.getBounds();
      const width = bounds.getEast() - bounds.getWest();
      if (width >= 360) throw new Error("Zoom in before saving an area of interest.");
      const area: ResearchArea = { id: crypto.randomUUID(), name: areaName.trim(), bounds: [normalizeLongitude(bounds.getWest()), bounds.getSouth(), normalizeLongitude(bounds.getEast()), bounds.getNorth()], basis: "operator-viewport", createdAt: new Date().toISOString() };
      setAreaError(null);
      if (await vault.update(existing => {
        if (existing.length >= 20) throw new Error("Maximum 20 saved research areas in this browser.");
        return [...existing, area];
      })) setAreaName("");
    } catch (failure) { setAreaError(failure instanceof Error ? failure.message : "Could not save research area."); }
  }

  async function unlockAreas() {
    setAreaError(null);
    const entered = passphrase;
    setPassphrase(""); setRepeatPassphrase("");
    await vault.unlock(entered, vault.state === "legacy");
  }

  return <>
    <div ref={container} className="world-map-canvas" data-testid="world-map-canvas" />
    {toolsHost && createPortal(<section className="world-map-tools" aria-label="World map tools">
      <button type="button" className="globe-action-button" aria-expanded={toolsOpen} onClick={() => setToolsOpen(value => !value)}>Map tools</button>
      {toolsOpen && <div className="world-map-tools__body">
        <label>Projection<select aria-label="Map projection" value={projection} onChange={event => setProjection(event.target.value as typeof projection)}><option value="globe">Globe</option><option value="mercator">Flat map</option></select></label>
        <button type="button" disabled={!ready} onClick={resetOverview}>Reset map view</button>
        <label><input type="checkbox" checked={imagery} onChange={event => setImagery(event.target.checked)} /> Satellite and street basemap</label>
        <p>Wide zoom uses NASA Blue Marble (historical composite). Closer zoom uses keyless Esri World Imagery, then OpenStreetMap if Esri is unreachable — the same keyless path as the reviewed God&apos;s Eye View reference. This is not a live satellite stream. Raster coverage ends at ±85.05°. Borders are de facto context, not legal boundaries.</p>
        <label>Find country<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Country name" /></label>
        {countries.map(country => <button type="button" key={country.id} onClick={() => {
          fit(coordinateBounds(country.rings.flat()));
        }}>{country.name}</button>)}
        {query.trim() && !countries.length && <p>No matching country in the reviewed context.</p>}
        <p>Areas are operator-defined viewport bounds, not event extents. Saved encrypted only in this browser; not included in database backups.</p>
        {vault.state === "legacy" && <p role="alert">Existing areas are unencrypted. Encrypt them with a new passphrase to continue. Failed migration leaves the original data unchanged.</p>}
        {vault.state !== "unlocked" && vault.state !== "invalid" && <>
          <label>Research-area passphrase<input type="password" autoComplete="off" value={passphrase} maxLength={128} onChange={event => setPassphrase(event.target.value)} /></label>
          {vault.state !== "locked" && <label>Repeat research-area passphrase<input type="password" autoComplete="off" value={repeatPassphrase} maxLength={128} onChange={event => setRepeatPassphrase(event.target.value)} /></label>}
          <p>Use 12–128 characters. Keep it separately: there is no passphrase recovery. Unlock again after closing World. Encryption does not protect an unlocked page.</p>
          <button type="button" disabled={vault.busy || passphrase.length < 12 || (vault.state !== "locked" && passphrase !== repeatPassphrase)} onClick={unlockAreas}>{vault.busy ? "Unlocking…" : vault.state === "legacy" ? "Encrypt existing research areas" : vault.state === "new" ? "Create encrypted area storage" : "Unlock research areas"}</button>
        </>}
        {vault.state === "unlocked" && <>
          <button type="button" onClick={() => { vault.lock(); setAreaName(""); setAreaError(null); }}>Lock research areas</button>
          <label>Research area name<input value={areaName} maxLength={80} onChange={event => setAreaName(event.target.value)} /></label>
          <button type="button" disabled={!ready || !areaName.trim() || vault.busy} onClick={saveArea}>Save current map area</button>
          {areas.map(area => <div key={area.id} className="flex gap-2"><button type="button" className="flex-1" onClick={() => fit(area.bounds)}>{area.name}</button><button type="button" aria-label={`Remove ${area.name}`} disabled={vault.busy} onClick={() => { setAreaError(null); void vault.update(existing => existing.filter(item => item.id !== area.id)); }}>Remove</button></div>)}
        </>}
        {(areaError || vault.error) && <p role="alert">{areaError || vault.error}</p>}
      </div>}
      <output aria-label="Map center coordinates">{coordinates}</output>
      {(!ready && !error) && <p role="status">Loading map engine…</p>}
      {error && <p role="alert">Map unavailable: {error}. The source-backed Browse list remains available.</p>}
      {tileError && imagery && <p role="status">Some imagery tiles are unavailable. Local vector context remains available when loaded; satellite coverage may be incomplete.</p>}
    </section>, toolsHost)}
  </>;
}
