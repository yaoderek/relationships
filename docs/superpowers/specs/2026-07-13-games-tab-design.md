# Games Tab — Design

**Date:** 2026-07-13
**Status:** APPROVED

## Overview

A new **Games** header tab with a game-picker dropdown and three guessing games built from the
user's real iMessage data in the local DuckDB. Score and streak are session-only (React state,
reset on reload or game switch). Everything runs locally; no network calls.

The three games:

1. **Who Said It** — read a ~5-message snippet from a 1:1 conversation, guess which friend it's
   with from 4 name choices.
2. **Finish the Convo** — see 4–5 context messages ending on a friend's message, pick your actual
   next reply from 4 options (1 real, 3 of your real replies pulled from other conversations,
   roughly length-matched).
3. **Who Says It More** — given a word both friends use, guess which of two friends says it more
   (rate-normalized), with counts revealed after.

## Approach

Server builds each complete round, including the answer, in one endpoint call. The frontend checks
answers locally. This is a single-player local app, so answer-in-payload "cheating" is a non-issue,
and it keeps the API to one round-trip per round.

Eligible people for all games: **top 20 contacts by 1:1 message volume**.

## Backend — `server/routes/games.py`

One new route file registered in `server/app.py`, following the existing inline-SQL + `run()`
pattern. Three endpoints, each returning a complete round:

### `GET /api/games/who-said-it`

- Pick a random person from the top 20.
- Pull a random contiguous run of ~5 messages from one session in that 1:1 chat.
- Filters: `text IS NOT NULL`, snippet contains at least 2 messages from the friend.
- Response: ordered messages (`text`, `is_from_me` only — no names), 4 shuffled person choices
  (`person_id`, `display_name`), correct `person_id`, and reveal info (date of the exchange).
- Names appearing inside snippet text are an accepted risk (part of the fun).

### `GET /api/games/finish-the-convo`

- Find a spot in a top-20 person's 1:1 chat where 4–5 context messages end on a friend message and
  the user's real reply follows within the same session.
- Real reply filters: length ≥ 8 chars, not attachment-only.
- Distractors: 3 of the user's real replies from *other* chats, within ±40% of the real reply's
  character length. Options deduped case-insensitively; regenerate if dedupe leaves < 4 options.
- Response: context messages, 4 shuffled reply options, correct index, and reveal payload
  (person name, date, next ~3 real messages after the reply).

### `GET /api/games/who-says-it-more`

- Candidate words: frequent non-stopword tokens across top-20 friends' messages.
- Pick a word and two friends who both use it, with meaningfully different rates.
- Rates normalized per 1,000 messages so heavy texters don't always win.
- Response: word, two choices (`person_id`, `display_name`), per-person counts and rates, and the
  correct `person_id`.

### Error handling

Each endpoint retries random sampling a few times; if no valid round is found, return 404 with a
clear `detail` message. The frontend renders this as "not enough message history for this game."

## Frontend

- `web/src/App.tsx`: add `<Link to="/games">Games</Link>` and
  `<Route path="/games" element={<Games />} />`.
- `web/src/api.ts`: round types and fetchers per existing convention.
- `web/src/pages/Games.tsx`: game-picker `<select>`, score/streak header
  (`correct / played` + current streak), and the round area.

Round flow: fetch round → render prompt (chat-bubble style for the two conversation games,
left/right aligned by `is_from_me`) → user clicks a choice → immediate reveal (green/red highlight,
correct answer, who/when, extra context messages) → "Next round" button.

## Testing

`tests/test_api_games.py` against the existing fixture DuckDB:

- Each endpoint returns a well-formed round: correct option counts, answer among options, no
  duplicate options, snippets meet filters.
- 404 behavior when the DB lacks eligible data.

## Out of scope

- Persisted stats or leaderboards.
- Redacting names inside snippet text.
- Group-chat rounds (1:1 only).
