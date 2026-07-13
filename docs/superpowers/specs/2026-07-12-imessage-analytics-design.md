# iMessage Analytics Dashboard — Design

**Status: APPROVED 2026-07-12** (with amendment: group chats added as a first-class dashboard section — see "Group chats" under Dashboard).

## Purpose

A personal, local-only macOS app for analyzing Derek's iMessage history: messaging frequency over time, broken out by person, plus relationship-level analytics (response times, initiation balance, activity heatmaps, long-term arcs). Built for one user first; the architecture keeps a clean extraction boundary so it can be packaged for a friend or two later.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Audience | Personal first; keep extraction layer clean so packaging for friends is easy later |
| Form factor | Local web dashboard (localhost, interactive) |
| Data freshness | Snapshot import — occasional manual full re-import, no incremental sync |
| Content depth (v1) | Metadata + light text stats (length, emoji, tapbacks); no NLP models in v1 |
| Architecture | Python ETL → DuckDB → FastAPI + React (Vite) |

## Source data

- `~/Library/Messages/chat.db` — SQLite, ~564MB on Derek's machine (likely several hundred thousand messages). Requires Full Disk Access (currently **not granted** to the agent environment — this is the first unblock).
- Per-message granularity available: nanosecond timestamps (sent / delivered / read), direction (`is_from_me`), service (iMessage vs SMS), full text (plain `text` column or `attributedBody` typedstream blob on newer macOS), tapbacks (`associated_message_type` 2000–2005), inline replies (`thread_originator_guid`), edits/unsends (Ventura+), attachments metadata, group-chat events.
- `~/Library/Application Support/AddressBook/` — contact names live here, not in chat.db. Joined by normalized phone/email; one person often maps to 2–3 handles.

## Shape of the system

Three layers, one hard boundary:

1. **Ingest pipeline** (Python CLI) — the only layer that touches Apple's data. Produces a clean local DuckDB file.
2. **API** (FastAPI) — reads only the DuckDB file; thin aggregate endpoints.
3. **Dashboard** (Vite + React) — talks only to the API. FastAPI serves the built frontend, so daily use is one command.

The ingest/analytics boundary is what makes future packaging cheap: a friend's setup is just the ingest step.

## Ingest pipeline (`python -m ingest`)

- Copy `chat.db` + WAL/SHM into local `data/`, open the **copy** read-only. Never touches the live DB.
- Decode text: `text` column when present, else decode the `attributedBody` typedstream blob (existing Python decoders handle this).
- Contacts: read AddressBook DB, normalize phone formats, map handles → contacts. One `person` per contact, merging multiple handles. Unmatched handles display as raw number; `overrides.yaml` allows manual merge/rename.
- Derive at ingest time: tapbacks split from real messages; conversation sessions (new session after 60-min gap); response-time pairs; char/word/emoji counts; Apple-epoch (ns since 2001-01-01) → UTC + local timestamps.
- Full rebuild each run — snapshot semantics, idempotent.

## Data model (DuckDB, `data/analytics.duckdb`)

- `persons` — person_id, display_name, source (contacts | unmatched | override)
- `handles` — handle_id, person_id, raw_id (phone/email), service
- `chats` — chat_id, name, is_group, participant count
- `messages` — msg_id, guid, chat_id, person_id, is_from_me, ts_utc, ts_local, date_delivered, date_read, service, text, char_len, word_count, emoji_count, has_attachment, is_audio, thread_originator_guid, session_id, response_seconds (nullable)
- `tapbacks` — tapback_id, target_msg_guid, person_id, kind, ts
- `attachments` — msg_id, mime_type, bytes (metadata only)

`data/` is gitignored; no message content ever enters the repo.

## API (FastAPI)

- `GET /api/persons` — list w/ totals, first/last message (feeds the picker)
- `GET /api/overview/timeseries?bucket=day|week|month`
- `GET /api/persons/{id}/timeseries?bucket=...`
- `GET /api/persons/{id}/stats` — sent/received balance, median & p90 response times both directions, initiation rate, streaks
- `GET /api/persons/{id}/heatmap` — hour × weekday matrix
- `GET /api/compare?ids=...` — overlay 2–5 people
- `GET /api/groups` — group leaderboard: totals, participant count, your share, first/last message
- `GET /api/groups/{id}/timeseries?bucket=...` — group volume trendline
- `GET /api/groups/{id}/heatmap` — hour × weekday matrix
- `GET /api/groups/{id}/stats` — share of voice per member, your participation rate, top tapback givers/receivers, busiest day ever, session counts

DuckDB queried live; no caching layer. Server binds to 127.0.0.1 only.

## Dashboard (React + Vite)

- **Overview** — total volume over time (sent/received), top-people leaderboard, "relationship arcs" chart of top ~10 people across the years.
- **Person detail** (core page) — time series with bucket toggle, hour × weekday heatmap, response-time distributions (you vs. them), balance and initiation stats, tapback/emoji favorites, message-length trend.
- **Compare** — overlay 2–5 people, normalized.
- **Group chats** — its own section, parallel to people:
  - **Leaderboard** — groups ranked by volume, with participant count, your share of messages, and recency.
  - **Group detail** — volume trendline (bucket toggle), hour × weekday heatmap, share-of-voice breakdown (who talks most), your participation rate over time, top tapback givers/receivers, message-length comparison across members, busiest-day callout.

## Judgment call: group chats vs. person metrics

Group chats are a first-class analytics section of their own (above). But per-person *relationship* metrics (response time, initiation, balance) still use **1:1 conversations only** — in a group chat a fast reply isn't necessarily a reply to you, so including groups corrupts exactly the metrics that matter. Group messages count in overview volume (tagged), and person pages get an "include group messages" toggle for raw counts only. Tapbacks count separately, never as messages.

## Edge cases & error handling

- Full Disk Access missing → ingest fails loudly with System Settings instructions.
- Edited messages use final text; unsent messages excluded.
- SMS and iMessage both included, tagged by service.
- Unknown handles remain visible by raw number, mergeable via `overrides.yaml`.

## Testing

Unit tests with fixtures for the fiddly pure functions: Apple-epoch conversion, phone normalization, typedstream decode, sessionization, response pairing, tapback classification. A tiny synthetic chat.db for an end-to-end ingest test; API tests against a fixture DuckDB. TDD throughout.

## Privacy

Everything local. Raw copies and the DuckDB live in gitignored `data/`. No message content leaves the machine; dashboard is localhost-only.

## Open items

- Full Disk Access grant (blocks any work against real data).
- Charting library choice (Recharts vs Observable Plot) deferred to implementation.
