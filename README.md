# relationships

Local-only analytics for your iMessage history: per-person and per-group
frequency, response times, heatmaps, and long-term trends. **Nothing leaves
your machine** — no accounts, no cloud, no telemetry. The dashboard runs on
`localhost` and reads a snapshot of your own Messages database.

## Get started (macOS)

Open **Terminal** (press `⌘ Space`, type "Terminal", hit Enter) and paste:

```bash
git clone https://github.com/yaoderek/relationships.git
cd relationships
./setup.sh
```

That's it. The script does everything else and tells you what it's doing at
each step:

1. **Installs the tools it needs** (a Python manager called `uv`, and Node.js)
   — only if you don't already have them.
2. **Builds the dashboard.**
3. **Asks macOS for permission to read your Messages.** This is the one
   manual step: macOS protects your message history behind a setting called
   **Full Disk Access**. The script opens the right System Settings pane for
   you, tells you exactly which toggle to flip, and continues automatically
   the moment you flip it. (This permission is why the analysis can stay
   100% local — *you* read your own data; no server ever sees it.)
4. **Ingests your messages** into a local database inside this folder
   (`data/analytics.duckdb`). Nothing is modified — it works from a copy.
5. **Opens the dashboard** in your browser at a `http://127.0.0.1:…` address
   that only your machine can reach.

First run takes a few minutes (mostly the ingest). When you're done, press
`Ctrl+C` in the terminal to stop the dashboard.

### Good to know

- **Want fresh data later?** Just run `./setup.sh` again. It skips everything
  that's already done and re-ingests your latest messages.
- **Want to try it before granting any permission?** Run `./setup.sh --demo`
  — it generates fake sample data and needs zero access to anything.
- **If macOS makes you restart your terminal** after granting Full Disk
  Access, no problem: run `./setup.sh` again and it picks up where it left
  off.
- **Wrong names or duplicate people in the dashboard?** Copy
  `overrides.example.yaml` to `overrides.yaml`, edit it, and re-run
  `./setup.sh`.

<details>
<summary>What the script runs under the hood (manual setup)</summary>

1. Grant **Full Disk Access** to your terminal:
   System Settings → Privacy & Security → Full Disk Access.
2. `uv sync`
3. `cd web && npm install && npm run build && cd ..`
4. `uv run python -m ingest` — snapshot chat.db → data/analytics.duckdb
5. `uv run python -m server` — dashboard at http://127.0.0.1:8000

</details>

## Development

- Python tests: `uv run pytest`
- Frontend: `cd web && npm run dev` (proxies /api to :8000) · tests: `npx vitest run`
- Design doc: `docs/superpowers/specs/2026-07-12-imessage-analytics-design.md`
