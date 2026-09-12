# Web API

FastAPI backend that exposes Lotbook data and analytics to the web UI and other
clients.

## Structure
- `app.py`: FastAPI app creation and router wiring.
- `auth.py`: API key auth helpers.
- `context.py`: Request context helpers.
- `diagnostics.py`: Diagnostics aggregation helpers.
- `summarizer.py`, `summarizer_rules.py`: Assistant summarization logic.
- `view_model.py`: Shared API view-model helpers.
- `routes/`: Route modules grouped by domain (clients, reports, intel, tools,
  trackers, assistant, maintenance, settings, health, stream).

## Usage notes
- All endpoints should live in `web_api/routes`.
- Keep responses JSON-ready and include `meta` payloads for provenance.
