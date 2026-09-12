# Web Source

Frontend source code for the Lotbook web UI.

## Layout
- `App.tsx`: App shell and routes.
- `main.tsx`: App bootstrap.
- `styles.css`: Global styles and Tailwind entry.
- `components/`: Shared UI and layout primitives.
- `pages/`: Page-level screens.
- `lib/`: API client, stream helpers, and reusable hooks.
- `design/`: Design tokens and visual system.
- `config/`: Navigation and app configuration.

## Usage notes
- Use `lib/api.ts` for all API calls.
- Pages must use the `AppShell` layout and shared components.
