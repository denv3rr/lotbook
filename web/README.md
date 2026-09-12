# Web

Vite + React frontend for Lotbook. This is the primary web UI and consumes the
shared API via `src/lib/api.ts`.

## Structure
- `src/main.tsx`: Browser entry point.
- `src/App.tsx`: App shell and routing.
- `src/pages/`: Page-level views (Dashboard, Clients, Intel, News, Reports,
  System, Trackers).
- `src/components/`: Shared layout and UI components.
- `src/lib/`: API client, streaming helpers, and shared utilities.
- `src/design/tokens.ts`: Design tokens and theming primitives.

## Local dev
```powershell
npm install
npm run dev
```

## Tests and build
```powershell
npm run test:e2e
npm run build
```

## Generated artifacts
- `dist/`: Build output (Vite).
- `test-results/`: Playwright run results.
