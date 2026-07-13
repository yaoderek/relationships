import argparse
import sqlite3
import sys
from pathlib import Path

import yaml

from .chatdb import copy_live_db, read_raw
from .contacts import read_contacts
from .load import build_analytics_db

_FDA_HELP = """\
ERROR: could not read {path}

This usually means Full Disk Access is missing. Fix:
  System Settings -> Privacy & Security -> Full Disk Access ->
  enable it for your terminal (or the app running this command), then retry.
"""


def run_ingest(source: Path, contacts_dir: Path, out: Path,
               overrides_path: Path | None) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        working_copy = copy_live_db(source, out.parent)
        raw = read_raw(working_copy)
    except (OSError, sqlite3.OperationalError, sqlite3.DatabaseError):
        print(_FDA_HELP.format(path=source), file=sys.stderr)
        raise SystemExit(1)
    contacts = read_contacts(contacts_dir) if contacts_dir.exists() else {}
    overrides = None
    if overrides_path and overrides_path.exists():
        overrides = yaml.safe_load(overrides_path.read_text())
    build_analytics_db(out, raw, contacts, overrides)
    real_count = sum(1 for m in raw.messages
                     if not m.get("associated_message_type")
                     and not m.get("item_type"))
    print(f"Ingested {real_count} messages from {len(raw.chats)} chats -> {out}")
    return real_count


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m ingest",
                                description="Snapshot chat.db into data/analytics.duckdb")
    home = Path.home()
    p.add_argument("--source", type=Path, default=home / "Library/Messages/chat.db")
    p.add_argument("--contacts-dir", type=Path,
                   default=home / "Library/Application Support/AddressBook")
    p.add_argument("--out", type=Path, default=Path("data/analytics.duckdb"))
    p.add_argument("--overrides", type=Path, default=Path("overrides.yaml"))
    args = p.parse_args()
    run_ingest(args.source, args.contacts_dir, args.out,
               args.overrides if args.overrides.exists() else None)


if __name__ == "__main__":
    main()
