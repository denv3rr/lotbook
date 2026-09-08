# Lib

Shared frontend utilities, API client, and data helpers.

## Files
- `api.ts`: Typed API client and caching helpers.
- `stream.ts`: Stream/WebSocket helpers.
- `maplibre.ts`, `mapDiagnostics.ts`: Map helpers and diagnostics; MapLibre CSS is injected only when the loader is used.
- `leaflet.ts`: Lazy Leaflet loader; fallback map CSS is injected only when the loader is used.
- `systemMetrics.ts`: System metrics formatting helpers.
- `trackerPause.ts`: Local pause toggle for tracker requests.
- `useMeasuredSize.ts`: Hook for measured layout sizing.

## Usage notes
- Route all API calls through `api.ts` for consistent headers and errors.
- API-key reads and writes are asynchronous because browser-stored values are
  encrypted. Await `getApiKey()` before creating HTTP headers or WebSocket
  subprotocols; never coerce its promise into a credential value.
- Encrypted key creation is serialized through one IndexedDB read/write
  transaction so simultaneous tabs reuse one key. If browser storage is
  unavailable, session requests fall back to page memory with an explicit UI
  warning; persistent-storage requests fail visibly and remain open for retry.
