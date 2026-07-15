# Friend Release — Productionization Design & Roadmap

**Status: DRAFT 2026-07-13.** Roadmap only; nothing here is built yet.

## Purpose

Take the personal iMessage analytics dashboard and make it releasable to friends, then the
world. Two hard constraints from the outset:

1. **Fully local, no accounts.** Everything already runs on-device against `chat.db`; keep it
   that way. No backend, no signup, no telemetry. "Nothing leaves your machine" is the pitch,
   not just the architecture.
2. **Setup must be nearly frictionless.** Today's flow (grant Full Disk Access to a terminal,
   install `uv`, `uv sync`, `npm install && npm run build`, run two commands) is a developer
   flow. A friend should go from download → seeing their own dashboard in under two minutes,
   with exactly one scary-looking permission step, guided.

Ease of use and virality are the optimization targets. Privacy is the enabler for both — people
will only run this on their real messages if the local-only story is airtight and legible.

## Where we are today

- Ingest (`python -m ingest`) → `data/analytics.duckdb` → FastAPI on `127.0.0.1:8000` serving
  built React app. Clean ingest/analytics boundary (by design — this was the plan all along).
- No packaging of any kind: no installer, no `.app`, no Docker, no signed binaries.
- Setup requires: `uv`, Node (to build the frontend), a terminal with Full Disk Access.
- Ingest is CLI-only: no progress reporting to the UI, errors print to stdout.
- Optional OpenAI day-summaries feature requires a `.env` API key (503 without it).
- No versioning, no update mechanism, no crash/error surface.

## The two problems that actually matter

### A. Local-only, no accounts — already true, needs to be *visibly* true

The architecture already satisfies this. The work is making it trustworthy and airtight:

- Server keeps binding `127.0.0.1` only. Never add an `0.0.0.0` option.
- The OpenAI day-summary feature is the one network egress. For the friend release it must be
  **off by default, clearly labeled, bring-your-own-key**, with a plain-English explanation of
  exactly what gets sent (message snippets from one day) before the first call. Consider
  shipping v1 to friends with it hidden entirely — one fewer thing to explain.
- Add a visible "privacy receipt" in the UI: where the data lives on disk (`data/`), what was
  read, confirmation that no network calls happen. This is a virality asset, not just
  reassurance — it's the screenshot people post when they recommend it.
- Optional later: a metadata-only ingest mode (no message text stored in DuckDB) for the
  cautious. Most analytics survive; text-derived stats (vocab, catchphrases) degrade gracefully.

### B. Setup flow — permission enablement is the whole game

Full Disk Access is per-*app* in macOS, and that drives the packaging decision. If a friend
runs ingest from Terminal, they're granting **Terminal** full disk access forever, which is both
scarier and worse hygiene than granting it to a single-purpose app. So the end state is a real
`.app`: the FDA grant is scoped to this one tool, and the System Settings pane shows a
recognizable name and icon instead of "Terminal".

The target first-run experience (in the packaged app):

1. Friend downloads a `.dmg` (or `brew install --cask relationships`), drags to Applications,
   opens it.
2. App opens a window (the existing React UI) straight into a **setup wizard**:
   - Step 1 — one screen explaining what the app reads and that nothing leaves the machine.
   - Step 2 — the app *tries* to read `chat.db`. On failure (the expected first-run state) it
     shows the FDA step: a button that deep-links to
     `x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles`, an inline
     screenshot/animation of the toggle, and the app polls for access in the background so the
     moment the toggle flips, the wizard auto-advances. No "restart the app and try again".
   - Step 3 — ingest runs with a real progress bar (messages copied / decoded / loaded) and a
     fun live counter ("142,318 messages and counting…"). This wait is the first-impression
     moment; make it delightful rather than a spinner.
   - Step 4 — land on the Overview page with their own data. Total time dominated by ingest.
3. Subsequent launches: open app → dashboard. A "Refresh data" button in the UI re-runs ingest
   (replacing "re-run the CLI"), showing the same progress UI.

That wizard is mostly work in layers we already own (a `/api/setup/status` endpoint, an ingest
progress channel, three React screens). The packaging shell around it is the new competency.

## Packaging decision

Options considered:

| Option | Setup friction | FDA story | Effort |
|---|---|---|---|
| Install script (`curl \| sh` installs uv, deps, builds web) | Medium — still terminal | Bad — grants FDA to Terminal | Low |
| Homebrew formula (CLI) | Medium | Bad — same Terminal problem | Low |
| PyInstaller single binary + browser | Low-medium | Poor — unsigned binary, Gatekeeper fight, FDA attaches to the binary but UX is clunky | Medium |
| **Native `.app` wrapping server + webview (Tauri sidecar or PyInstaller + menubar shell)** | **Lowest — drag to Applications** | **Best — FDA scoped to the app, deep-link + poll works cleanly** | High |

**Decision: phase it.** Ship an install script to the first 2–3 technical friends immediately
(cheap, validates the analytics are compelling on other people's data and other macOS
versions), while building the `.app` as the real release vehicle. The install script is
throwaway by design; don't polish it.

For the `.app` shell, leading candidate is **Tauri v2 with the Python server as a sidecar
binary** (PyInstaller-frozen ingest+server, web dist embedded). The app is a thin native shell:
launch sidecar on a free port, open webview, manage the FDA flow, quit sidecar on close.
Alternative if Tauri fights us: a Swift/SwiftUI menubar wrapper doing the same thing. Decide by
prototyping the sidecar boot in a day; don't commit in this doc.

Signing and notarization are **not optional** for virality: an unsigned app means every friend
hits "Apple could not verify…" and needs the right-click-open ritual — that kills the share
loop. Requires an Apple Developer account ($99/yr) and a notarization step in the build. Budget
this early; it's the most annoying part of macOS distribution.

## Productionization gap list

Beyond packaging and the wizard, in rough priority order:

1. **Ingest robustness across machines.** `chat.db` schema varies by macOS version, and we've
   only ever run against one machine. Every friend install is a schema fuzz test. Needs:
   defensive column handling, a preflight "can I parse this?" check, and an error report the
   friend can send back (stack trace + macOS version + schema fingerprint, **zero message
   content**).
2. **Error surfacing in the UI.** Today errors die in the terminal. The app has no terminal.
   Every failure mode (FDA revoked, disk full, corrupt copy, empty AddressBook) needs a
   human-readable in-UI state with a next step.
3. **Ingest progress channel.** Ingest currently prints; the wizard needs structured progress
   (SSE or polling a status endpoint). Also enables the "Refresh data" button.
4. **Port handling.** Fixed :8000 will collide. The app shell should pick a free port and pass
   it to the webview.
5. **Contact overrides in the UI.** `overrides.yaml` is developer UX. Friends need at minimum a
   "merge these two people / rename" affordance in the People page, writing the same overrides
   file and re-deriving. Can ship after v1 to friends if the contact matching hit rate proves
   high enough.
6. **Versioning and updates.** Tag releases, embed version in UI, add an update check
   (static JSON on GitHub Pages — a version check is not telemetry, but make it opt-out and say
   so). Auto-update (Sparkle / Tauri updater) can come later; "download the new dmg" is fine
   for friends.
7. **CI.** None exists. GitHub Actions: pytest + vitest + a build job producing the signed,
   notarized `.dmg` artifact. The release build must be reproducible by CI, not by Derek's
   laptop.
8. **A tiny bit of legal hygiene** before "the world": license choice (if open-sourcing — which
   itself is a trust/virality lever worth taking), and a short plain-English privacy statement
   in the repo and the app.

## Virality mechanics

The product is inherently share-y — the numbers are about *relationships*, so every screenshot
implicates a second person who then wants their own. Lean into that, carefully:

- **Share cards.** One-tap export of a rendered image for the fun stats — top people, streaks,
  "wrapped"-style year recap, group share-of-voice. Rules: **opt-in, aggregate numbers only,
  never message text**, names editable/redactable before export, and a small app-name
  watermark with the download URL. This is the growth loop.
- **A "Year Wrapped" page** timed as a seasonal moment is the single highest-leverage feature
  for spread; it composes almost entirely from existing analytics.
- **Demo mode as the landing pitch.** `make_demo.py` already exists — surface it as "try with
  sample data" in the wizard so someone can see the product before granting any permission.
  Lowers the trust threshold for the FDA ask.
- **The privacy story is the marketing.** "Open source, local-only, we can prove nothing leaves
  your machine" is the differentiator against any cloud competitor and the reason people feel
  safe posting about it.

## Roadmap

**Phase 0 — Friends-of-friends alpha (install script), ~days**
- Install script (checks for uv/node, installs, builds, prints FDA instructions).
- Ship to 2–3 technical friends. Goal: validate ingest against foreign `chat.db`s and macOS
  versions; collect the failure catalog that drives gap item #1.
- Hide/flag off the OpenAI feature.

**Phase 1 — The wizard and the hardening, ~1–2 weeks**
- Setup wizard flow in the web UI (status endpoint, FDA detection + deep link + poll, ingest
  progress, refresh button).
- Ingest robustness + in-UI error states from the Phase 0 failure catalog.
- Free-port selection; version stamp in UI.

**Phase 2 — The `.app`, ~2–3 weeks**
- Prototype Tauri sidecar boot; commit to shell approach.
- PyInstaller-freeze ingest+server; embed web dist; wire lifecycle (launch/quit/port).
- Apple Developer account, signing + notarization, `.dmg` build in CI.
- Test matrix: last 3 macOS versions × Apple Silicon (Intel only if a friend actually has one).

**Phase 3 — Friend release proper**
- Ship the `.dmg` to the full friend group. Watch setup completion rate — the metric that
  matters is "% of people who get from download to seeing their dashboard unassisted".
- Contact merge/rename UI if override friction shows up.

**Phase 4 — World**
- Landing page (demo data screenshots, privacy statement, download).
- Share cards + Wrapped page.
- Open-source decision, license, README rewrite for end users vs. developers.
- Homebrew cask, update check.

## Explicitly out of scope

- Any server/cloud component, accounts, or sync. Ever, per constraint.
- Windows/Linux — no `chat.db`, no product.
- Incremental ingest. Full-rebuild snapshot semantics stay; it's fast enough and simpler than
  cursoring, and the "Refresh data" button makes it invisible.
- NLP/embedding features. Orthogonal to release readiness.

## Open questions

- Tauri sidecar vs. Swift shell — settle with a one-day spike (Phase 2 entry gate).
- Does the AddressBook contact-match rate hold up on other people's machines? Phase 0 answers
  this and determines how urgent the merge UI is.
- App name. "relationships" is a repo name, not an app name; needs one before signing
  certificates and the dmg get minted.
