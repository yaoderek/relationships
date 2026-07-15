# relationships

Local iMessage analytics. Runs on your machine, nothing leaves it.

## Setup (macOS)

```bash
git clone https://github.com/yaoderek/relationships.git
cd relationships
./setup.sh
```

The script will ask you to grant Full Disk Access, then open the dashboard
at `http://127.0.0.1:8000`. `Ctrl+C` to stop.

- Re-run `./setup.sh` anytime for fresh data.
- `./setup.sh --demo` uses fake data, no permissions needed.
- To rename/merge people: copy `overrides.example.yaml` → `overrides.yaml`, edit, re-run.

## Optional AI features

Needs an OpenAI key. Put it in `.env` (created by setup):

```
OPENAI_API_KEY=sk-your-key
```

Then:

```bash
uv run python scripts/language.py
uv run python scripts/semantic.py
```

## Development

- Python tests: `uv run pytest`
- Frontend: `cd web && npm run dev` · tests: `npx vitest run`
