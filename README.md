# relationships

Local-only analytics for your iMessage history: per-person and per-group
frequency, response times, heatmaps, and long-term trends. Nothing leaves
your machine.

## Setup (macOS)

1. Grant **Full Disk Access** to your terminal:
   System Settings → Privacy & Security → Full Disk Access.
2. `uv sync`
3. `cd web && npm install && npm run build && cd ..`

## Use

```bash
uv run python -m ingest        # snapshot chat.db → data/analytics.duckdb
uv run python -m server        # dashboard at http://127.0.0.1:8000
```

Re-run the ingest whenever you want fresh data. To fix unmatched numbers or
merge duplicate people, copy `overrides.example.yaml` to `overrides.yaml`,
edit, re-ingest.

No Messages data? `uv run python scripts/make_demo.py` generates a synthetic
dataset to explore the dashboard.

## Development

- Python tests: `uv run pytest`
- Frontend: `cd web && npm run dev` (proxies /api to :8000) · tests: `npx vitest run`
- Design doc: `docs/superpowers/specs/2026-07-12-imessage-analytics-design.md`
