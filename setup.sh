#!/usr/bin/env bash
# One-command setup for the relationships dashboard.
#
#   ./setup.sh          real data (needs Full Disk Access, guided below)
#   ./setup.sh --demo   synthetic data, no permissions needed
#
# Safe to re-run: completed steps are fast no-ops, so if macOS makes you
# restart your terminal after granting Full Disk Access, just run it again.
set -euo pipefail
cd "$(dirname "$0")"

BOLD=$(tput bold 2>/dev/null || true)
DIM=$(tput dim 2>/dev/null || true)
RESET=$(tput sgr0 2>/dev/null || true)

step() { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
note() { printf '%s    %s%s\n' "$DIM" "$1" "$RESET"; }
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

DEMO=0
[[ "${1:-}" == "--demo" ]] && DEMO=1

[[ "$(uname)" == "Darwin" ]] || fail "This only works on macOS (it reads the Messages database)."

CHAT_DB="$HOME/Library/Messages/chat.db"

# TCC (Full Disk Access) denies at open() time, so actually try to read a byte
# rather than trusting `test -r`.
can_read_chat_db() { head -c 1 "$CHAT_DB" >/dev/null 2>&1; }

terminal_app_name() {
  case "${TERM_PROGRAM:-}" in
    Apple_Terminal) echo "Terminal" ;;
    iTerm.app)      echo "iTerm" ;;
    vscode)         echo "your editor (VS Code / Cursor)" ;;
    WarpTerminal)   echo "Warp" ;;
    *)              echo "the terminal app you're using right now" ;;
  esac
}

step "1/5 Checking for uv (Python package manager)"
if ! command -v uv >/dev/null 2>&1; then
  note "uv not found — installing from astral.sh"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv installed but not on PATH. Open a new terminal and re-run ./setup.sh"
fi
note "uv $(uv --version | awk '{print $2}')"

step "2/5 Checking for Node.js"
if ! command -v npm >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    note "Node not found — installing with Homebrew"
    brew install node
  else
    fail "Node.js is required to build the dashboard. Install it from https://nodejs.org (or install Homebrew and re-run), then run ./setup.sh again."
  fi
fi
note "node $(node --version)"

step "3/5 Installing dependencies and building the dashboard"
uv sync
(cd web && npm install --no-fund --no-audit && npm run build)

DB_PATH="data/analytics.duckdb"
if [[ "$DEMO" == "1" ]]; then
  step "4/5 Generating demo data (no Messages access needed)"
  # Separate file so demo mode never clobbers a real ingest.
  DB_PATH="data/demo_analytics.duckdb"
  uv run python scripts/make_demo.py --out "$DB_PATH"
else
  step "4/5 Reading your Messages database"
  if ! can_read_chat_db; then
    APP_NAME=$(terminal_app_name)
    cat <<EOF

  macOS protects your Messages history, so you need to grant
  ${BOLD}Full Disk Access${RESET} to ${BOLD}${APP_NAME}${RESET}. This stays on your machine —
  the app never sends anything anywhere (feel free to check the code).

  Opening System Settings now. In the window that appears:

    1. Find ${BOLD}${APP_NAME}${RESET} in the list (click ${BOLD}+${RESET} to add it if missing)
    2. Flip its toggle ${BOLD}on${RESET}
    3. If macOS asks to quit the app, choose "Later" — or quit,
       reopen, and run ${BOLD}./setup.sh${RESET} again (it picks up where it left off)

EOF
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" || true
    printf '  Waiting for access'
    for _ in $(seq 1 90); do
      if can_read_chat_db; then break; fi
      printf '.'
      sleep 2
    done
    printf '\n'
    if ! can_read_chat_db; then
      fail "Still can't read $CHAT_DB.
If you flipped the toggle, quit and reopen your terminal, then run ./setup.sh again.
(Everything installed so far is saved — it will jump straight to this step.)"
    fi
    note "Access granted."
  fi
  uv run python -m ingest
fi

step "5/5 Starting the dashboard"
PORT=8000
while (echo >"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; do
  PORT=$((PORT + 1))
  [[ $PORT -gt 8020 ]] && fail "No free port found between 8000 and 8020."
done
note "http://127.0.0.1:$PORT  (Ctrl+C to stop; run ./setup.sh again anytime for fresh data)"
(sleep 1.5 && open "http://127.0.0.1:$PORT") &
exec uv run python -m server --db "$DB_PATH" --port "$PORT"
