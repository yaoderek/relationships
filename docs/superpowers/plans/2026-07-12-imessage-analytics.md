# iMessage Analytics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local macOS web dashboard analyzing Derek's iMessage history — per-person and per-group frequency, response times, heatmaps, and long-term trends — fed by a snapshot ingest of `chat.db` into DuckDB.

**Architecture:** Three layers with a hard boundary: a Python ingest CLI (the only code touching Apple's data) writes a clean DuckDB file; a FastAPI server reads only that file and exposes aggregate endpoints; a Vite+React dashboard consumes the API. FastAPI serves the built frontend in production.

**Tech Stack:** Python ≥3.11 (uv), DuckDB, FastAPI + uvicorn, `emoji`, PyYAML, pytest + httpx; Node ≥20, Vite + React + TypeScript, Recharts, react-router-dom, vitest.

**Spec:** `docs/superpowers/specs/2026-07-12-imessage-analytics-design.md`

## Global Constraints

- macOS only. Source data: `~/Library/Messages/chat.db` (requires Full Disk Access) and `~/Library/Application Support/AddressBook/`.
- Everything stays local. Server binds `127.0.0.1` only. No message content ever leaves the machine.
- `data/` is gitignored (already in `.gitignore`); never commit real message content. **Tests use synthetic fixtures only — never the real chat.db.**
- Ingest opens only a *copy* of chat.db, read-only. Never touch the live DB.
- Per-person relationship metrics (response time, initiation, balance) use 1:1 chats only. Group chats get their own analytics section. Tapbacks never count as messages.
- Charting library: **Recharts** (locked in; spec left it open).
- Python env via `uv` (`uv sync`, `uv run pytest`). Frontend via `npm` inside `web/`.
- TDD: every task writes the failing test first. Commit at the end of every task.
- Before writing any chart component (Tasks 14–16), the implementer MUST read the `dataviz` skill.

## File Structure

```
relationships/
├── pyproject.toml            # Python project + deps (Task 1)
├── overrides.example.yaml    # sample manual merge/rename file (Task 8)
├── ingest/
│   ├── __init__.py
│   ├── __main__.py           # CLI: python -m ingest (Task 9)
│   ├── apple_epoch.py        # Apple ns-epoch → datetime (Task 1)
│   ├── handles.py            # phone/email normalization (Task 2)
│   ├── typedstream.py        # attributedBody text decoder (Task 3)
│   ├── textstats.py          # char/word/emoji stats (Task 4)
│   ├── chatdb.py             # copy live DB + read raw rows (Task 5)
│   ├── contacts.py           # AddressBook → handle→name map (Task 6)
│   ├── derive.py             # tapbacks, sessions, response times (Task 7)
│   └── load.py               # person resolution + DuckDB writer (Task 8)
├── server/
│   ├── __init__.py
│   ├── __main__.py           # python -m server → uvicorn on 127.0.0.1 (Task 17)
│   ├── app.py                # FastAPI factory + static mount (Task 10)
│   ├── db.py                 # read-only DuckDB query helper (Task 10)
│   └── routes/
│       ├── __init__.py
│       ├── persons.py        # persons list/timeseries/stats/heatmap/compare (Tasks 10–11)
│       ├── overview.py       # overall timeseries (Task 11)
│       └── groups.py         # group leaderboard/timeseries/heatmap/stats (Task 12)
├── tests/
│   ├── __init__.py
│   ├── fixtures.py           # synthetic chat.db + AddressBook builders (Tasks 5–6)
│   ├── conftest.py           # session-scoped analytics.duckdb from fixtures (Task 10)
│   ├── test_apple_epoch.py … test_api_groups.py  # one per module
└── web/                      # Vite React TS app (Tasks 13–16)
    ├── vite.config.ts        # dev proxy /api → 127.0.0.1:8000
    └── src/
        ├── api.ts            # typed fetch client
        ├── lib/format.ts     # duration/label formatting (+ vitest)
        ├── components/       # TimeSeries.tsx, Heatmap.tsx, Leaderboard.tsx
        └── pages/            # Overview, Person, Compare, Groups, GroupDetail
```

---

### Task 1: Python scaffolding + Apple epoch conversion

**Files:**
- Create: `pyproject.toml`, `ingest/__init__.py`, `tests/__init__.py`, `ingest/apple_epoch.py`, `tests/test_apple_epoch.py`

**Interfaces:**
- Produces: `apple_to_utc(raw: int | None) -> datetime | None` — converts chat.db `date` values (nanoseconds since 2001-01-01 UTC on modern macOS, plain seconds on pre-2017 rows) to tz-aware UTC datetimes. `0`/`None` → `None`. Also exports `APPLE_EPOCH: datetime`.

- [ ] **Step 1: Create project files**

`pyproject.toml`:

```toml
[project]
name = "relationships"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "duckdb>=1.0",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "emoji>=2.12",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create empty `ingest/__init__.py` and `tests/__init__.py`.

Run: `cd /Users/yaoderek/Desktop/relationships && uv sync`
Expected: environment created, deps installed.

- [ ] **Step 2: Write the failing test**

`tests/test_apple_epoch.py`:

```python
from datetime import datetime, timezone

from ingest.apple_epoch import APPLE_EPOCH, apple_to_utc


def test_nanosecond_value():
    # 2023-03-15 12:00:00 UTC = unix 1678881600; minus unix(2001-01-01)=978307200
    # → 700,574,400 s after the Apple epoch
    raw = 700_574_400 * 10**9
    assert apple_to_utc(raw) == datetime(2023, 3, 15, 12, 0, tzinfo=timezone.utc)


def test_legacy_seconds_value():
    # pre-High Sierra rows store plain seconds
    raw = 700_574_400
    assert apple_to_utc(raw) == datetime(2023, 3, 15, 12, 0, tzinfo=timezone.utc)


def test_zero_and_none_are_none():
    assert apple_to_utc(0) is None
    assert apple_to_utc(None) is None


def test_epoch_constant():
    assert APPLE_EPOCH == datetime(2001, 1, 1, tzinfo=timezone.utc)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_apple_epoch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.apple_epoch'`

- [ ] **Step 4: Write minimal implementation**

`ingest/apple_epoch.py`:

```python
from datetime import datetime, timedelta, timezone

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# Values above this are nanoseconds; below, legacy whole seconds.
_NS_THRESHOLD = 10**12


def apple_to_utc(raw: int | None) -> datetime | None:
    if not raw:
        return None
    seconds = raw / 1e9 if raw > _NS_THRESHOLD else float(raw)
    return APPLE_EPOCH + timedelta(seconds=seconds)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_apple_epoch.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock ingest/ tests/
git commit -m "feat: project scaffolding + Apple epoch conversion"
```

---

### Task 2: Handle normalization

**Files:**
- Create: `ingest/handles.py`, `tests/test_handles.py`

**Interfaces:**
- Produces: `normalize_handle(raw: str) -> str` — emails lowercase; phones reduced to digits with US country code `1` stripped from 11-digit numbers. Used as the join key between chat.db handles and AddressBook entries.

- [ ] **Step 1: Write the failing test**

`tests/test_handles.py`:

```python
from ingest.handles import normalize_handle


def test_email_lowercased():
    assert normalize_handle(" Alice@Example.COM ") == "alice@example.com"


def test_us_phone_variants_collapse():
    assert normalize_handle("+1 (555) 123-4567") == "5551234567"
    assert normalize_handle("15551234567") == "5551234567"
    assert normalize_handle("555-123-4567") == "5551234567"


def test_international_number_keeps_digits():
    assert normalize_handle("+44 20 7946 0958") == "442079460958"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handles.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

`ingest/handles.py`:

```python
def normalize_handle(raw: str) -> str:
    raw = raw.strip().lower()
    if "@" in raw:
        return raw
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_handles.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/handles.py tests/test_handles.py
git commit -m "feat: handle normalization for contact matching"
```

---

### Task 3: attributedBody typedstream decoder

**Files:**
- Create: `ingest/typedstream.py`, `tests/test_typedstream.py`

**Interfaces:**
- Produces: `decode_attributed_body(blob: bytes | None) -> str | None` — extracts the plain text from the `attributedBody` NSAttributedString typedstream blob that newer macOS versions use instead of the `text` column. Returns `None` when the blob is empty or unparseable.

The format: the UTF-8 text sits after the literal bytes `NSString` plus a 5-byte marker `\x01\x94\x84\x01\x2b`, preceded by a length: one byte if < 0x80, `\x81` + 2-byte little-endian, or `\x82` + 4-byte little-endian.

- [ ] **Step 1: Write the failing test**

`tests/test_typedstream.py`:

```python
from ingest.typedstream import decode_attributed_body

MARKER = b"\x01\x94\x84\x01\x2b"


def _blob(text: bytes, length_bytes: bytes) -> bytes:
    return b"\x04\x0bstreamtyped\x81junkNSString" + MARKER + length_bytes + text + b"\x86trailer"


def test_short_string():
    assert decode_attributed_body(_blob(b"hello", bytes([5]))) == "hello"


def test_two_byte_length():
    text = b"x" * 300
    blob = _blob(text, b"\x81" + (300).to_bytes(2, "little"))
    assert decode_attributed_body(blob) == "x" * 300


def test_four_byte_length():
    text = b"y" * 70000
    blob = _blob(text, b"\x82" + (70000).to_bytes(4, "little"))
    assert decode_attributed_body(blob) == "y" * 70000


def test_unicode_text():
    text = "héllo 🎉".encode()
    assert decode_attributed_body(_blob(text, bytes([len(text)]))) == "héllo 🎉"


def test_garbage_and_empty_return_none():
    assert decode_attributed_body(None) is None
    assert decode_attributed_body(b"") is None
    assert decode_attributed_body(b"no marker here") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_typedstream.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

`ingest/typedstream.py`:

```python
_PREFIX = b"NSString"
_MARKER_LEN = 5  # \x01\x94\x84\x01\x2b after the class name


def decode_attributed_body(blob: bytes | None) -> str | None:
    if not blob:
        return None
    idx = blob.find(_PREFIX)
    if idx == -1:
        return None
    pos = idx + len(_PREFIX) + _MARKER_LEN
    if pos >= len(blob):
        return None
    marker = blob[pos]
    if marker == 0x81:
        length = int.from_bytes(blob[pos + 1 : pos + 3], "little")
        pos += 3
    elif marker == 0x82:
        length = int.from_bytes(blob[pos + 1 : pos + 5], "little")
        pos += 5
    else:
        length = marker
        pos += 1
    return blob[pos : pos + length].decode("utf-8", errors="replace")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_typedstream.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/typedstream.py tests/test_typedstream.py
git commit -m "feat: attributedBody typedstream text decoder"
```

---

### Task 4: Text stats (chars / words / emoji)

**Files:**
- Create: `ingest/textstats.py`, `tests/test_textstats.py`

**Interfaces:**
- Produces: `text_stats(text: str | None) -> tuple[int, int, int]` — `(char_len, word_count, emoji_count)`; `(0, 0, 0)` for `None`/empty. `list_emojis(text: str | None) -> list[str]` — every emoji occurrence in order (duplicates preserved), used to populate the `emoji_uses` table.

- [ ] **Step 1: Write the failing test**

`tests/test_textstats.py`:

```python
from ingest.textstats import list_emojis, text_stats


def test_plain_text():
    assert text_stats("hello there world") == (17, 3, 0)


def test_emoji_counted():
    chars, words, emojis = text_stats("lol 😂😂 nice 🎉")
    assert emojis == 3
    assert words == 4


def test_none_and_empty():
    assert text_stats(None) == (0, 0, 0)
    assert text_stats("") == (0, 0, 0)


def test_list_emojis_keeps_duplicates():
    assert list_emojis("😂 ok 😂🎉") == ["😂", "😂", "🎉"]
    assert list_emojis(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_textstats.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

`ingest/textstats.py`:

```python
import emoji


def text_stats(text: str | None) -> tuple[int, int, int]:
    if not text:
        return (0, 0, 0)
    return (len(text), len(text.split()), emoji.emoji_count(text))


def list_emojis(text: str | None) -> list[str]:
    if not text:
        return []
    return [m["emoji"] for m in emoji.emoji_list(text)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_textstats.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/textstats.py tests/test_textstats.py
git commit -m "feat: text stats (chars, words, emoji)"
```

---

### Task 5: Synthetic chat.db fixture + chat.db reader

**Files:**
- Create: `tests/fixtures.py`, `ingest/chatdb.py`, `tests/test_chatdb.py`

**Interfaces:**
- Produces (fixtures): `make_chat_db(path: Path, handles, chats, chat_handles, messages, attachments=())` — builds a minimal-but-real chat.db-shaped SQLite file. `handles`: list of `(handle_id, id, service)`. `chats`: list of `(chat_id, display_name, style)` where style 43=group, 45=1:1. `chat_handles`: list of `(chat_id, handle_id)`. `messages`: list of dicts with keys `msg_id, guid, text, attributedBody, handle_id, chat_id, date, date_read, date_delivered, is_from_me, service, associated_message_type, associated_message_guid, item_type, cache_has_attachments, is_audio_message, thread_originator_guid` (missing keys default to 0/None/""). `attachments`: list of `(msg_id, mime_type, total_bytes)`. Also `apple_ns(dt: datetime) -> int` for building timestamps.
- Produces (chatdb): `copy_live_db(src: Path, dest_dir: Path) -> Path` (copies db + `-wal`/`-shm` siblings); `read_raw(db_path: Path) -> RawData`; `RawData` dataclass with fields `handles: list[dict]` (keys handle_id, id, service), `chats: list[dict]` (chat_id, display_name, style), `chat_handles: list[tuple[int, int]]`, `messages: list[dict]` (all keys listed above), `attachments: list[dict]` (msg_id, mime_type, total_bytes).

- [ ] **Step 1: Write the fixture builder** (infrastructure — exercised by this task's tests)

`tests/fixtures.py`:

```python
import sqlite3
from datetime import datetime
from pathlib import Path

from ingest.apple_epoch import APPLE_EPOCH

_MSG_DEFAULTS = {
    "text": None, "attributedBody": None, "handle_id": 0, "date_read": 0,
    "date_delivered": 0, "is_from_me": 0, "service": "iMessage",
    "associated_message_type": 0, "associated_message_guid": None,
    "item_type": 0, "cache_has_attachments": 0, "is_audio_message": 0,
    "thread_originator_guid": None,
}


def apple_ns(dt: datetime) -> int:
    return int((dt - APPLE_EPOCH).total_seconds() * 1e9)


def make_chat_db(path: Path, handles, chats, chat_handles, messages, attachments=()):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT, service TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT, chat_identifier TEXT,
                           display_name TEXT, style INTEGER);
        CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT,
            attributedBody BLOB, handle_id INTEGER, date INTEGER, date_read INTEGER,
            date_delivered INTEGER, is_from_me INTEGER, service TEXT,
            associated_message_type INTEGER, associated_message_guid TEXT,
            item_type INTEGER, cache_has_attachments INTEGER,
            is_audio_message INTEGER, thread_originator_guid TEXT);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        CREATE TABLE attachment (ROWID INTEGER PRIMARY KEY, mime_type TEXT, total_bytes INTEGER);
        CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
    """)
    conn.executemany("INSERT INTO handle VALUES (?,?,?)", handles)
    conn.executemany(
        "INSERT INTO chat VALUES (?,?,?,?,?)",
        [(cid, f"guid-{cid}", f"ident-{cid}", name, style) for cid, name, style in chats],
    )
    conn.executemany("INSERT INTO chat_handle_join VALUES (?,?)", chat_handles)
    for m in messages:
        row = {**_MSG_DEFAULTS, **m}
        conn.execute(
            """INSERT INTO message VALUES (:msg_id,:guid,:text,:attributedBody,:handle_id,
               :date,:date_read,:date_delivered,:is_from_me,:service,
               :associated_message_type,:associated_message_guid,:item_type,
               :cache_has_attachments,:is_audio_message,:thread_originator_guid)""",
            row,
        )
        conn.execute("INSERT INTO chat_message_join VALUES (?,?)", (row["chat_id"], row["msg_id"]))
    for i, (msg_id, mime, size) in enumerate(attachments, start=1):
        conn.execute("INSERT INTO attachment VALUES (?,?,?)", (i, mime, size))
        conn.execute("INSERT INTO message_attachment_join VALUES (?,?)", (msg_id, i))
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Write the failing test**

`tests/test_chatdb.py`:

```python
from datetime import datetime, timezone

from ingest.chatdb import copy_live_db, read_raw
from tests.fixtures import apple_ns, make_chat_db

TS = datetime(2024, 6, 1, 15, 30, tzinfo=timezone.utc)


def _build(tmp_path):
    db = tmp_path / "chat.db"
    make_chat_db(
        db,
        handles=[(1, "+15551234567", "iMessage")],
        chats=[(1, None, 45)],
        chat_handles=[(1, 1)],
        messages=[
            {"msg_id": 10, "guid": "g-10", "text": "hi", "handle_id": 1,
             "chat_id": 1, "date": apple_ns(TS)},
            {"msg_id": 11, "guid": "g-11", "text": "yo", "handle_id": 0,
             "chat_id": 1, "date": apple_ns(TS), "is_from_me": 1,
             "cache_has_attachments": 1},
        ],
        attachments=[(11, "image/jpeg", 12345)],
    )
    return db


def test_read_raw(tmp_path):
    raw = read_raw(_build(tmp_path))
    assert [h["id"] for h in raw.handles] == ["+15551234567"]
    assert raw.chats[0]["style"] == 45
    assert raw.chat_handles == [(1, 1)]
    assert len(raw.messages) == 2
    incoming = next(m for m in raw.messages if m["msg_id"] == 10)
    assert incoming["chat_id"] == 1 and incoming["text"] == "hi"
    assert raw.attachments == [{"msg_id": 11, "mime_type": "image/jpeg", "total_bytes": 12345}]


def test_copy_live_db_copies_wal(tmp_path):
    src = _build(tmp_path)
    (tmp_path / "chat.db-wal").write_bytes(b"wal")
    dest = copy_live_db(src, tmp_path / "work")
    assert dest.exists() and dest != src
    assert (tmp_path / "work" / "chat.db-wal").read_bytes() == b"wal"
    assert len(read_raw(dest).messages) == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_chatdb.py -v`
Expected: FAIL — `ingest.chatdb` not found

- [ ] **Step 4: Write minimal implementation**

`ingest/chatdb.py`:

```python
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_MESSAGE_SQL = """
    SELECT m.ROWID AS msg_id, m.guid, m.text, m.attributedBody, m.handle_id,
           m.date, m.date_read, m.date_delivered, m.is_from_me, m.service,
           m.associated_message_type, m.associated_message_guid, m.item_type,
           m.cache_has_attachments, m.is_audio_message, m.thread_originator_guid,
           cmj.chat_id
    FROM message m JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
"""

_ATTACHMENT_SQL = """
    SELECT maj.message_id AS msg_id, a.mime_type, a.total_bytes
    FROM attachment a JOIN message_attachment_join maj ON maj.attachment_id = a.ROWID
"""


@dataclass
class RawData:
    handles: list[dict]
    chats: list[dict]
    chat_handles: list[tuple[int, int]]
    messages: list[dict]
    attachments: list[dict]


def copy_live_db(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    for suffix in ("-wal", "-shm"):
        sidecar = src.with_name(src.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, dest_dir / sidecar.name)
    return dest


def read_raw(db_path: Path) -> RawData:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return RawData(
            handles=[dict(r) for r in conn.execute(
                "SELECT ROWID AS handle_id, id, service FROM handle")],
            chats=[dict(r) for r in conn.execute(
                "SELECT ROWID AS chat_id, display_name, style FROM chat")],
            chat_handles=[(r["chat_id"], r["handle_id"]) for r in conn.execute(
                "SELECT chat_id, handle_id FROM chat_handle_join")],
            messages=[dict(r) for r in conn.execute(_MESSAGE_SQL)],
            attachments=[dict(r) for r in conn.execute(_ATTACHMENT_SQL)],
        )
    finally:
        conn.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_chatdb.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add ingest/chatdb.py tests/fixtures.py tests/test_chatdb.py
git commit -m "feat: chat.db safety copy + raw reader with synthetic fixture"
```

---

### Task 6: AddressBook contacts reader

**Files:**
- Create: `ingest/contacts.py`, `tests/test_contacts.py`
- Modify: `tests/fixtures.py` (append `make_addressbook_db`)

**Interfaces:**
- Consumes: `normalize_handle` from Task 2.
- Produces: `read_contacts(addressbook_dir: Path) -> dict[str, str]` — maps *normalized* handle → display name, scanning every `AddressBook-v22.abcddb` under the dir (macOS keeps one per source under `Sources/<uuid>/`). Fixture: `make_addressbook_db(path: Path, people)` where `people` is a list of `(first, last, phones: list[str], emails: list[str])`.

- [ ] **Step 1: Append fixture builder to `tests/fixtures.py`**

```python
def make_addressbook_db(path: Path, people):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ZABCDRECORD (Z_PK INTEGER PRIMARY KEY, ZFIRSTNAME TEXT,
                                  ZLASTNAME TEXT, ZORGANIZATION TEXT);
        CREATE TABLE ZABCDPHONENUMBER (ZOWNER INTEGER, ZFULLNUMBER TEXT);
        CREATE TABLE ZABCDEMAILADDRESS (ZOWNER INTEGER, ZADDRESS TEXT);
    """)
    for pk, (first, last, phones, emails) in enumerate(people, start=1):
        conn.execute("INSERT INTO ZABCDRECORD VALUES (?,?,?,NULL)", (pk, first, last))
        conn.executemany("INSERT INTO ZABCDPHONENUMBER VALUES (?,?)",
                         [(pk, p) for p in phones])
        conn.executemany("INSERT INTO ZABCDEMAILADDRESS VALUES (?,?)",
                         [(pk, e) for e in emails])
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Write the failing test**

`tests/test_contacts.py`:

```python
from ingest.contacts import read_contacts
from tests.fixtures import make_addressbook_db


def test_reads_phones_and_emails_normalized(tmp_path):
    make_addressbook_db(
        tmp_path / "Sources" / "abc" / "AddressBook-v22.abcddb",
        people=[
            ("Alice", "Smith", ["+1 (555) 123-4567"], ["Alice@Example.com"]),
            ("Bob", None, ["555-999-0000"], []),
        ],
    )
    contacts = read_contacts(tmp_path)
    assert contacts["5551234567"] == "Alice Smith"
    assert contacts["alice@example.com"] == "Alice Smith"
    assert contacts["5559990000"] == "Bob"


def test_multiple_sources_merged_first_wins(tmp_path):
    make_addressbook_db(tmp_path / "Sources" / "a" / "AddressBook-v22.abcddb",
                        people=[("Alice", "Smith", ["5551234567"], [])])
    make_addressbook_db(tmp_path / "Sources" / "b" / "AddressBook-v22.abcddb",
                        people=[("Alicia", "S", ["5551234567"], [])])
    contacts = read_contacts(tmp_path)
    assert contacts["5551234567"] in ("Alice Smith", "Alicia S")  # deterministic per sort


def test_empty_dir(tmp_path):
    assert read_contacts(tmp_path) == {}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_contacts.py -v`
Expected: FAIL — `ingest.contacts` not found

- [ ] **Step 4: Write minimal implementation**

`ingest/contacts.py`:

```python
import sqlite3
from pathlib import Path

from .handles import normalize_handle

_QUERY = """
    SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, p.ZFULLNUMBER AS raw
    FROM ZABCDRECORD r JOIN ZABCDPHONENUMBER p ON p.ZOWNER = r.Z_PK
    UNION ALL
    SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, e.ZADDRESS AS raw
    FROM ZABCDRECORD r JOIN ZABCDEMAILADDRESS e ON e.ZOWNER = r.Z_PK
"""


def read_contacts(addressbook_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for db in sorted(addressbook_dir.glob("**/AddressBook-v22.abcddb")):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for first, last, org, raw in conn.execute(_QUERY):
                if not raw:
                    continue
                name = " ".join(part for part in (first, last) if part) or org
                if name:
                    mapping.setdefault(normalize_handle(raw), name)
        finally:
            conn.close()
    return mapping
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_contacts.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add ingest/contacts.py tests/fixtures.py tests/test_contacts.py
git commit -m "feat: AddressBook contacts reader"
```

---

### Task 7: Derivations — tapbacks, sessions, response times

**Files:**
- Create: `ingest/derive.py`, `tests/test_derive.py`

**Interfaces:**
- Consumes: raw message dicts shaped as `RawData.messages` (Task 5).
- Produces:
  - `TAPBACK_KINDS: dict[int, str]` — `{2000: "love", 2001: "like", 2002: "dislike", 2003: "laugh", 2004: "emphasize", 2005: "question"}`
  - `split_tapbacks(messages: list[dict]) -> tuple[list[dict], list[dict]]` — `(real, tapbacks)`. Real = `associated_message_type == 0 and item_type == 0`. Tapbacks get key `target_guid` (the `associated_message_guid` with `p:N/` or `bp:` prefix stripped) and `kind`. Removal rows (3000s) and system events are dropped.
  - `assign_sessions(rows: list[dict], gap_minutes: int = 60) -> None` — mutates rows (each has `chat_id`, `ts_utc`), setting `session_id` = `"{chat_id}:{n}"`; a new session starts when the gap from the previous message in the same chat exceeds `gap_minutes`.
  - `compute_response_seconds(rows: list[dict], is_group: dict[int, bool]) -> None` — mutates rows, setting `response_seconds` (float) on a message when, within a 1:1 chat and the same session, the previous message had the opposite `is_from_me`; else `None`.

- [ ] **Step 1: Write the failing test**

`tests/test_derive.py`:

```python
from datetime import datetime, timedelta, timezone

from ingest.derive import assign_sessions, compute_response_seconds, split_tapbacks

T0 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _row(chat_id, minutes, from_me):
    return {"chat_id": chat_id, "ts_utc": T0 + timedelta(minutes=minutes),
            "is_from_me": from_me}


def test_split_tapbacks():
    msgs = [
        {"msg_id": 1, "associated_message_type": 0, "item_type": 0},
        {"msg_id": 2, "associated_message_type": 2003, "item_type": 0,
         "associated_message_guid": "p:0/ABC-123"},
        {"msg_id": 3, "associated_message_type": 2000, "item_type": 0,
         "associated_message_guid": "bp:DEF-456"},
        {"msg_id": 4, "associated_message_type": 3003, "item_type": 0,
         "associated_message_guid": "p:0/ABC-123"},          # removal → dropped
        {"msg_id": 5, "associated_message_type": 0, "item_type": 2},  # group event → dropped
    ]
    real, tapbacks = split_tapbacks(msgs)
    assert [m["msg_id"] for m in real] == [1]
    assert [(t["kind"], t["target_guid"]) for t in tapbacks] == [
        ("laugh", "ABC-123"), ("love", "DEF-456")]


def test_sessions_split_on_gap():
    rows = [_row(1, 0, 0), _row(1, 10, 1), _row(1, 200, 0), _row(2, 5, 0)]
    assign_sessions(rows, gap_minutes=60)
    assert rows[0]["session_id"] == rows[1]["session_id"] == "1:0"
    assert rows[2]["session_id"] == "1:1"
    assert rows[3]["session_id"] == "2:0"


def test_response_seconds_direction_flip_only():
    rows = [_row(1, 0, 0), _row(1, 2, 1), _row(1, 3, 1), _row(1, 200, 0)]
    assign_sessions(rows)
    compute_response_seconds(rows, is_group={1: False})
    assert rows[0]["response_seconds"] is None          # first message
    assert rows[1]["response_seconds"] == 120.0         # flip: reply in 2 min
    assert rows[2]["response_seconds"] is None          # same sender again
    assert rows[3]["response_seconds"] is None          # new session


def test_response_seconds_skips_groups():
    rows = [_row(9, 0, 0), _row(9, 1, 1)]
    assign_sessions(rows)
    compute_response_seconds(rows, is_group={9: True})
    assert rows[1]["response_seconds"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_derive.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

`ingest/derive.py`:

```python
from collections import defaultdict

TAPBACK_KINDS = {2000: "love", 2001: "like", 2002: "dislike",
                 2003: "laugh", 2004: "emphasize", 2005: "question"}


def _strip_target_guid(guid: str | None) -> str:
    if not guid:
        return ""
    if "/" in guid:
        return guid.split("/", 1)[1]
    return guid.removeprefix("bp:")


def split_tapbacks(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    real, tapbacks = [], []
    for m in messages:
        assoc = m.get("associated_message_type") or 0
        if assoc in TAPBACK_KINDS:
            tapbacks.append({**m, "kind": TAPBACK_KINDS[assoc],
                             "target_guid": _strip_target_guid(m.get("associated_message_guid"))})
        elif assoc == 0 and (m.get("item_type") or 0) == 0:
            real.append(m)
        # anything else (tapback removals, system/group events) is dropped
    return real, tapbacks


def assign_sessions(rows: list[dict], gap_minutes: int = 60) -> None:
    by_chat = defaultdict(list)
    for r in rows:
        by_chat[r["chat_id"]].append(r)
    for chat_id, chat_rows in by_chat.items():
        chat_rows.sort(key=lambda r: r["ts_utc"])
        session = 0
        prev_ts = None
        for r in chat_rows:
            if prev_ts is not None and (r["ts_utc"] - prev_ts).total_seconds() > gap_minutes * 60:
                session += 1
            r["session_id"] = f"{chat_id}:{session}"
            prev_ts = r["ts_utc"]


def compute_response_seconds(rows: list[dict], is_group: dict[int, bool]) -> None:
    by_chat = defaultdict(list)
    for r in rows:
        r.setdefault("response_seconds", None)
        by_chat[r["chat_id"]].append(r)
    for chat_id, chat_rows in by_chat.items():
        if is_group.get(chat_id):
            continue
        chat_rows.sort(key=lambda r: r["ts_utc"])
        for prev, cur in zip(chat_rows, chat_rows[1:]):
            if (cur["session_id"] == prev["session_id"]
                    and bool(cur["is_from_me"]) != bool(prev["is_from_me"])):
                cur["response_seconds"] = (cur["ts_utc"] - prev["ts_utc"]).total_seconds()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_derive.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/derive.py tests/test_derive.py
git commit -m "feat: derive tapbacks, sessions, response times"
```

---

### Task 8: Person resolution + DuckDB loader

**Files:**
- Create: `ingest/load.py`, `tests/test_load.py`, `overrides.example.yaml`

**Interfaces:**
- Consumes: everything from Tasks 1–7 (`apple_to_utc`, `normalize_handle`, `decode_attributed_body`, `text_stats`, `list_emojis`, `RawData`, `split_tapbacks`, `assign_sessions`, `compute_response_seconds`).
- Produces:
  - `resolve_persons(handles: list[dict], contacts: dict[str, str], overrides: dict | None) -> tuple[list[dict], dict[int, int]]` — `(persons, handle_person)`. `persons`: dicts `{person_id, display_name, source}` where source ∈ `contacts | unmatched | override`; handles sharing a contact name merge into one person. `handle_person`: handle_id → person_id. Overrides dict shape: `{"merge": [{"name": str, "handles": [str]}], "rename": {str: str}}`.
  - `build_analytics_db(out_path: Path, raw: RawData, contacts: dict[str, str], overrides: dict | None = None) -> None` — writes the full DuckDB file. Tables (exact DDL below): `persons`, `handles`, `chats`, `chat_members`, `messages`, `tapbacks`, `attachments`, `emoji_uses`.
  - Message attribution rule: incoming → sender's person_id; outgoing in a 1:1 chat → the counterpart's person_id; outgoing in a group → NULL.
  - `ts_local` is the system-local wall time (naive); `ts_utc` naive UTC.

DDL used by `build_analytics_db`:

```sql
CREATE TABLE persons (person_id INTEGER, display_name TEXT, source TEXT);
CREATE TABLE handles (handle_id INTEGER, person_id INTEGER, raw_id TEXT, service TEXT);
CREATE TABLE chats (chat_id INTEGER, name TEXT, is_group BOOLEAN, participant_count INTEGER);
CREATE TABLE chat_members (chat_id INTEGER, person_id INTEGER);
CREATE TABLE messages (
    msg_id BIGINT, guid TEXT, chat_id INTEGER, person_id INTEGER, is_from_me BOOLEAN,
    ts_utc TIMESTAMP, ts_local TIMESTAMP, date_delivered TIMESTAMP, date_read TIMESTAMP,
    service TEXT, text TEXT, char_len INTEGER, word_count INTEGER, emoji_count INTEGER,
    has_attachment BOOLEAN, is_audio BOOLEAN, thread_originator_guid TEXT,
    session_id TEXT, response_seconds DOUBLE);
CREATE TABLE tapbacks (target_guid TEXT, person_id INTEGER, is_from_me BOOLEAN,
                       kind TEXT, ts_utc TIMESTAMP);
CREATE TABLE attachments (msg_id BIGINT, mime_type TEXT, total_bytes BIGINT);
CREATE TABLE emoji_uses (msg_id BIGINT, emoji TEXT);
```

- [ ] **Step 1: Write the failing test**

`tests/test_load.py`:

```python
from datetime import datetime, timezone

import duckdb

from ingest.chatdb import read_raw
from ingest.load import build_analytics_db, resolve_persons
from tests.fixtures import apple_ns, make_chat_db

T = lambda h, m: datetime(2024, 6, 1, h, m, tzinfo=timezone.utc)


def test_resolve_persons_merges_contact_handles():
    handles = [{"handle_id": 1, "id": "+15551234567", "service": "iMessage"},
               {"handle_id": 2, "id": "alice@example.com", "service": "iMessage"},
               {"handle_id": 3, "id": "+15559990000", "service": "SMS"}]
    contacts = {"5551234567": "Alice Smith", "alice@example.com": "Alice Smith"}
    persons, handle_person = resolve_persons(handles, contacts, None)
    assert handle_person[1] == handle_person[2] != handle_person[3]
    by_id = {p["person_id"]: p for p in persons}
    assert by_id[handle_person[1]]["display_name"] == "Alice Smith"
    assert by_id[handle_person[3]] == {"person_id": handle_person[3],
                                       "display_name": "+15559990000",
                                       "source": "unmatched"}


def test_resolve_persons_overrides():
    handles = [{"handle_id": 1, "id": "+15551111111", "service": "SMS"},
               {"handle_id": 2, "id": "+15552222222", "service": "SMS"}]
    overrides = {"merge": [{"name": "Gym Buddy",
                            "handles": ["+15551111111", "+15552222222"]}],
                 "rename": {}}
    persons, handle_person = resolve_persons(handles, {}, overrides)
    assert handle_person[1] == handle_person[2]
    assert persons[0]["display_name"] == "Gym Buddy"
    assert persons[0]["source"] == "override"


def _build_chat_db(tmp_path):
    db = tmp_path / "chat.db"
    make_chat_db(
        db,
        handles=[(1, "+15551234567", "iMessage"), (2, "+15559990000", "iMessage")],
        chats=[(1, None, 45), (2, "the squad", 43)],
        chat_handles=[(1, 1), (2, 1), (2, 2)],
        messages=[
            # 1:1 with Alice: her msg, then my reply 2 min later with an emoji
            {"msg_id": 1, "guid": "g1", "text": "hey 😂", "handle_id": 1,
             "chat_id": 1, "date": apple_ns(T(12, 0))},
            {"msg_id": 2, "guid": "g2", "text": "yo!", "handle_id": 0,
             "chat_id": 1, "date": apple_ns(T(12, 2)), "is_from_me": 1},
            # her tapback on my reply
            {"msg_id": 3, "guid": "g3", "handle_id": 1, "chat_id": 1,
             "date": apple_ns(T(12, 3)), "associated_message_type": 2000,
             "associated_message_guid": "p:0/g2"},
            # group chat: one from Bob, one from me
            {"msg_id": 4, "guid": "g4", "text": "group hi", "handle_id": 2,
             "chat_id": 2, "date": apple_ns(T(13, 0))},
            {"msg_id": 5, "guid": "g5", "text": "sup", "handle_id": 0,
             "chat_id": 2, "date": apple_ns(T(13, 1)), "is_from_me": 1},
        ],
        attachments=[(2, "image/png", 999)],
    )
    return db


def test_build_analytics_db(tmp_path):
    raw = read_raw(_build_chat_db(tmp_path))
    out = tmp_path / "analytics.duckdb"
    build_analytics_db(out, raw, contacts={"5551234567": "Alice Smith"})
    con = duckdb.connect(str(out), read_only=True)

    assert con.execute("SELECT count(*) FROM persons").fetchone()[0] == 2
    assert con.execute(
        "SELECT is_group FROM chats ORDER BY chat_id").fetchall() == [(False,), (True,)]
    assert con.execute("SELECT count(*) FROM messages").fetchone()[0] == 4  # tapback excluded

    # my 1:1 reply is attributed to Alice and has a 120s response time
    pid_alice = con.execute(
        "SELECT person_id FROM persons WHERE display_name='Alice Smith'").fetchone()[0]
    row = con.execute(
        "SELECT person_id, response_seconds, has_attachment FROM messages WHERE guid='g2'"
    ).fetchone()
    assert row == (pid_alice, 120.0, True)

    # my group message has no person attribution
    assert con.execute(
        "SELECT person_id FROM messages WHERE guid='g5'").fetchone() == (None,)

    assert con.execute(
        "SELECT kind, is_from_me FROM tapbacks").fetchall() == [("love", False)]
    assert con.execute(
        "SELECT emoji FROM emoji_uses").fetchall() == [("😂",)]
    assert con.execute(
        "SELECT participant_count FROM chats WHERE chat_id=2").fetchone() == (2,)
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_load.py -v`
Expected: FAIL — `ingest.load` not found

- [ ] **Step 3: Write the implementation**

`ingest/load.py`:

```python
from pathlib import Path

import duckdb

from .apple_epoch import apple_to_utc
from .chatdb import RawData
from .derive import assign_sessions, compute_response_seconds, split_tapbacks
from .handles import normalize_handle
from .textstats import list_emojis, text_stats
from .typedstream import decode_attributed_body

_DDL = """
CREATE TABLE persons (person_id INTEGER, display_name TEXT, source TEXT);
CREATE TABLE handles (handle_id INTEGER, person_id INTEGER, raw_id TEXT, service TEXT);
CREATE TABLE chats (chat_id INTEGER, name TEXT, is_group BOOLEAN, participant_count INTEGER);
CREATE TABLE chat_members (chat_id INTEGER, person_id INTEGER);
CREATE TABLE messages (
    msg_id BIGINT, guid TEXT, chat_id INTEGER, person_id INTEGER, is_from_me BOOLEAN,
    ts_utc TIMESTAMP, ts_local TIMESTAMP, date_delivered TIMESTAMP, date_read TIMESTAMP,
    service TEXT, text TEXT, char_len INTEGER, word_count INTEGER, emoji_count INTEGER,
    has_attachment BOOLEAN, is_audio BOOLEAN, thread_originator_guid TEXT,
    session_id TEXT, response_seconds DOUBLE);
CREATE TABLE tapbacks (target_guid TEXT, person_id INTEGER, is_from_me BOOLEAN,
                       kind TEXT, ts_utc TIMESTAMP);
CREATE TABLE attachments (msg_id BIGINT, mime_type TEXT, total_bytes BIGINT);
CREATE TABLE emoji_uses (msg_id BIGINT, emoji TEXT);
"""


def resolve_persons(handles, contacts, overrides):
    overrides = overrides or {}
    forced = {}
    for entry in overrides.get("merge", []):
        for h in entry["handles"]:
            forced[normalize_handle(h)] = entry["name"]
    persons, handle_person, key_to_id = [], {}, {}
    for h in handles:
        norm = normalize_handle(h["id"])
        if norm in forced:
            key, name, source = "name:" + forced[norm], forced[norm], "override"
        elif norm in contacts:
            key, name, source = "name:" + contacts[norm], contacts[norm], "contacts"
        else:
            key, name, source = "raw:" + norm, h["id"], "unmatched"
        if key not in key_to_id:
            key_to_id[key] = len(persons) + 1
            persons.append({"person_id": key_to_id[key], "display_name": name,
                            "source": source})
        handle_person[h["handle_id"]] = key_to_id[key]
    renames = overrides.get("rename") or {}
    norm_renames = {normalize_handle(k): v for k, v in renames.items()}
    for h in handles:
        new_name = norm_renames.get(normalize_handle(h["id"]))
        if new_name:
            persons[handle_person[h["handle_id"]] - 1]["display_name"] = new_name
    return persons, handle_person


def _naive_utc(dt):
    return dt.replace(tzinfo=None) if dt else None


def _naive_local(dt):
    return dt.astimezone().replace(tzinfo=None) if dt else None


def build_analytics_db(out_path: Path, raw: RawData, contacts, overrides=None) -> None:
    persons, handle_person = resolve_persons(raw.handles, contacts, overrides)

    is_group = {c["chat_id"]: c["style"] == 43 for c in raw.chats}
    members: dict[int, set[int]] = {}
    for chat_id, handle_id in raw.chat_handles:
        members.setdefault(chat_id, set()).add(handle_person[handle_id])
    counterpart = {cid: next(iter(pids)) for cid, pids in members.items()
                   if not is_group.get(cid) and len(pids) == 1}

    real, raw_tapbacks = split_tapbacks(raw.messages)

    rows = []
    emoji_rows = []
    for m in real:
        ts = apple_to_utc(m["date"])
        if ts is None:
            continue
        text = m["text"] or decode_attributed_body(m["attributedBody"])
        chars, words, emojis = text_stats(text)
        sender = handle_person.get(m["handle_id"])
        person_id = counterpart.get(m["chat_id"]) if m["is_from_me"] else sender
        rows.append({
            "msg_id": m["msg_id"], "guid": m["guid"], "chat_id": m["chat_id"],
            "person_id": person_id, "is_from_me": bool(m["is_from_me"]),
            "ts_utc": ts, "text": text, "char_len": chars, "word_count": words,
            "emoji_count": emojis,
            "date_delivered": apple_to_utc(m["date_delivered"]),
            "date_read": apple_to_utc(m["date_read"]),
            "service": m["service"],
            "has_attachment": bool(m["cache_has_attachments"]),
            "is_audio": bool(m["is_audio_message"]),
            "thread_originator_guid": m["thread_originator_guid"],
        })
        emoji_rows += [(m["msg_id"], e) for e in list_emojis(text)]

    assign_sessions(rows)
    compute_response_seconds(rows, is_group)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    con = duckdb.connect(str(out_path))
    con.execute(_DDL)
    con.executemany("INSERT INTO persons VALUES (?,?,?)",
                    [(p["person_id"], p["display_name"], p["source"]) for p in persons])
    con.executemany("INSERT INTO handles VALUES (?,?,?,?)",
                    [(h["handle_id"], handle_person[h["handle_id"]], h["id"], h["service"])
                     for h in raw.handles])
    con.executemany("INSERT INTO chats VALUES (?,?,?,?)",
                    [(c["chat_id"], c["display_name"], is_group[c["chat_id"]],
                      len(members.get(c["chat_id"], ())))
                     for c in raw.chats])
    con.executemany("INSERT INTO chat_members VALUES (?,?)",
                    [(cid, pid) for cid, pids in members.items() for pid in pids])
    con.executemany(
        """INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r["msg_id"], r["guid"], r["chat_id"], r["person_id"], r["is_from_me"],
          _naive_utc(r["ts_utc"]), _naive_local(r["ts_utc"]),
          _naive_utc(r["date_delivered"]), _naive_utc(r["date_read"]),
          r["service"], r["text"], r["char_len"], r["word_count"], r["emoji_count"],
          r["has_attachment"], r["is_audio"], r["thread_originator_guid"],
          r["session_id"], r["response_seconds"]) for r in rows])
    con.executemany("INSERT INTO tapbacks VALUES (?,?,?,?,?)",
                    [(t["target_guid"], handle_person.get(t["handle_id"]),
                      bool(t["is_from_me"]), t["kind"],
                      _naive_utc(apple_to_utc(t["date"]))) for t in raw_tapbacks])
    con.executemany("INSERT INTO attachments VALUES (?,?,?)",
                    [(a["msg_id"], a["mime_type"], a["total_bytes"])
                     for a in raw.attachments]) if raw.attachments else None
    con.executemany("INSERT INTO emoji_uses VALUES (?,?)", emoji_rows) if emoji_rows else None
    con.close()
```

`overrides.example.yaml`:

```yaml
# Copy to overrides.yaml (gitignored is fine) and edit.
# merge: force several raw handles into one named person.
merge:
  - name: "Gym Buddy"
    handles: ["+15551111111", "+15552222222"]
# rename: change the display name for whoever owns a handle.
rename:
  "+15559990000": "Mom (old number)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_load.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add ingest/load.py tests/test_load.py overrides.example.yaml
git commit -m "feat: person resolution + DuckDB analytics loader"
```

---

### Task 9: Ingest CLI + end-to-end test

**Files:**
- Create: `ingest/__main__.py`, `tests/test_ingest_e2e.py`

**Interfaces:**
- Consumes: `copy_live_db`, `read_raw` (Task 5), `read_contacts` (Task 6), `build_analytics_db` (Task 8).
- Produces: `run_ingest(source: Path, contacts_dir: Path, out: Path, overrides_path: Path | None) -> int` returning the message count, and a `python -m ingest` CLI with flags `--source` (default `~/Library/Messages/chat.db`), `--contacts-dir` (default `~/Library/Application Support/AddressBook`), `--out` (default `data/analytics.duckdb`), `--overrides` (default `overrides.yaml` if present). Missing Full Disk Access → exit code 1 with instructions.

- [ ] **Step 1: Write the failing test**

`tests/test_ingest_e2e.py`:

```python
import duckdb
import pytest

from ingest.__main__ import run_ingest
from tests.fixtures import apple_ns, make_addressbook_db, make_chat_db
from datetime import datetime, timezone

T = lambda m: datetime(2024, 6, 1, 12, m, tzinfo=timezone.utc)


def test_end_to_end(tmp_path):
    chat = tmp_path / "chat.db"
    make_chat_db(
        chat,
        handles=[(1, "+15551234567", "iMessage")],
        chats=[(1, None, 45)],
        chat_handles=[(1, 1)],
        messages=[{"msg_id": 1, "guid": "g1", "text": "hello", "handle_id": 1,
                   "chat_id": 1, "date": apple_ns(T(0))}],
    )
    make_addressbook_db(tmp_path / "ab" / "Sources" / "x" / "AddressBook-v22.abcddb",
                        people=[("Alice", "Smith", ["+15551234567"], [])])
    out = tmp_path / "data" / "analytics.duckdb"

    count = run_ingest(chat, tmp_path / "ab", out, overrides_path=None)

    assert count == 1
    con = duckdb.connect(str(out), read_only=True)
    assert con.execute("SELECT display_name FROM persons").fetchone() == ("Alice Smith",)
    con.close()
    # source untouched, copy went to out's directory
    assert chat.exists() and (out.parent / "chat.db").exists()


def test_missing_source_raises_helpful_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        run_ingest(tmp_path / "nope.db", tmp_path, tmp_path / "out.duckdb", None)
    assert exc.value.code == 1
    assert "Full Disk Access" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_e2e.py -v`
Expected: FAIL — no `run_ingest`

- [ ] **Step 3: Write the implementation**

`ingest/__main__.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_e2e.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/__main__.py tests/test_ingest_e2e.py
git commit -m "feat: ingest CLI with end-to-end test"
```

---

### Task 10: FastAPI scaffolding + persons leaderboard endpoint

**Files:**
- Create: `server/__init__.py`, `server/app.py`, `server/db.py`, `server/routes/__init__.py`, `server/routes/persons.py`, `server/routes/overview.py`, `server/routes/groups.py` (the last two as empty routers, filled by Tasks 11–12), `tests/conftest.py`, `tests/test_api_persons.py`

**Interfaces:**
- Consumes: `build_analytics_db`, `read_raw`, fixtures (Tasks 5–8).
- Produces:
  - `server.db.run(db_path: Path, sql: str, params: list | None = None) -> list[tuple]` — opens DuckDB read-only per call, closes after.
  - `server.db.bucket_expr(bucket: str, col: str = "m.ts_local") -> str` — validated (`day|week|month`, else HTTPException 422) `strftime(date_trunc(...), '%Y-%m-%d')` SQL fragment.
  - `server.app.create_app(db_path: Path) -> FastAPI` — mounts all routers under `/api`; serves `web/dist` statically at `/` if it exists; stores `db_path` on `app.state`.
  - `GET /api/persons` → `[{person_id, display_name, total, sent, received, first_ts, last_ts}]`, 1:1 messages only, ordered by total desc.
  - conftest fixtures `analytics_db` and `client` (session-scoped) over the canonical synthetic dataset below — **all API tests in Tasks 10–12 assert against this exact dataset.**

- [ ] **Step 1: Write conftest with the canonical dataset**

`tests/conftest.py`:

```python
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingest.chatdb import read_raw
from ingest.load import build_analytics_db
from server.app import create_app
from tests.fixtures import apple_ns, make_chat_db

# Deterministic ts_local regardless of machine timezone.
os.environ["TZ"] = "UTC"
time.tzset()


def _t(day, hour, minute):
    return apple_ns(datetime(2024, 6, day, hour, minute, tzinfo=timezone.utc))


@pytest.fixture(scope="session")
def analytics_db(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("api")
    chat = tmp / "chat.db"
    make_chat_db(
        chat,
        handles=[(1, "+15551234567", "iMessage"), (2, "+15559990000", "iMessage")],
        chats=[(1, None, 45), (2, "the squad", 43), (3, None, 45)],
        chat_handles=[(1, 1), (2, 1), (2, 2), (3, 2)],
        messages=[
            # 1:1 with Alice — Jun 1: her msg, my reply 2 min later; Jun 2: I initiate, she replies in 5 min
            {"msg_id": 1, "guid": "g1", "text": "hey 😂", "handle_id": 1,
             "chat_id": 1, "date": _t(1, 12, 0)},
            {"msg_id": 2, "guid": "g2", "text": "yo!", "handle_id": 0,
             "chat_id": 1, "date": _t(1, 12, 2), "is_from_me": 1},
            {"msg_id": 3, "guid": "g3", "text": "morning", "handle_id": 0,
             "chat_id": 1, "date": _t(2, 9, 0), "is_from_me": 1},
            {"msg_id": 4, "guid": "g4", "text": "hi", "handle_id": 1,
             "chat_id": 1, "date": _t(2, 9, 5)},
            # 1:1 with Bob — one incoming
            {"msg_id": 5, "guid": "g5", "text": "sup", "handle_id": 2,
             "chat_id": 3, "date": _t(1, 18, 0)},
            # group "the squad" — Alice, Bob, me, one message each
            {"msg_id": 6, "guid": "g6", "text": "group hi", "handle_id": 1,
             "chat_id": 2, "date": _t(1, 13, 0)},
            {"msg_id": 7, "guid": "g7", "text": "hello all", "handle_id": 2,
             "chat_id": 2, "date": _t(1, 13, 1)},
            {"msg_id": 8, "guid": "g8", "text": "sup squad", "handle_id": 0,
             "chat_id": 2, "date": _t(1, 13, 2), "is_from_me": 1},
            # tapbacks: Alice loves my g2; Bob laughs at my g8
            {"msg_id": 9, "guid": "g9", "handle_id": 1, "chat_id": 1,
             "date": _t(1, 12, 3), "associated_message_type": 2000,
             "associated_message_guid": "p:0/g2"},
            {"msg_id": 10, "guid": "g10", "handle_id": 2, "chat_id": 2,
             "date": _t(1, 13, 3), "associated_message_type": 2003,
             "associated_message_guid": "p:0/g8"},
        ],
    )
    out = tmp / "analytics.duckdb"
    build_analytics_db(out, read_raw(chat),
                       contacts={"5551234567": "Alice Smith",
                                 "5559990000": "Bob Jones"})
    return out


@pytest.fixture(scope="session")
def client(analytics_db):
    return TestClient(create_app(analytics_db))
```

Dataset cheat sheet (used by all API assertions): Alice 1:1 = 4 msgs (2 sent / 2 received), my reply 120s, her reply 300s, sessions Jun 1 (she starts) + Jun 2 (I start). Bob 1:1 = 1 received. Group = 3 msgs (1 each), 1 session, Jun 1 13:00–13:02. Overview Jun 1 = 6 msgs (2 sent / 4 received), Jun 2 = 2 (1/1). 2024-06-01 is a Saturday (`dayofweek` = 6), 06-02 Sunday (= 0).

- [ ] **Step 2: Write the failing test**

`tests/test_api_persons.py`:

```python
def test_persons_leaderboard(client):
    people = client.get("/api/persons").json()
    assert [p["display_name"] for p in people] == ["Alice Smith", "Bob Jones"]
    alice, bob = people
    assert (alice["total"], alice["sent"], alice["received"]) == (4, 2, 2)
    assert (bob["total"], bob["sent"], bob["received"]) == (1, 0, 1)
    assert alice["first_ts"].startswith("2024-06-01")
    assert alice["last_ts"].startswith("2024-06-02")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_api_persons.py -v`
Expected: FAIL — `server.app` not found

- [ ] **Step 4: Write the implementation**

`server/db.py`:

```python
from pathlib import Path

import duckdb
from fastapi import HTTPException

_BUCKETS = {"day", "week", "month"}


def run(db_path: Path, sql: str, params: list | None = None) -> list[tuple]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def bucket_expr(bucket: str, col: str = "m.ts_local") -> str:
    if bucket not in _BUCKETS:
        raise HTTPException(status_code=422,
                            detail=f"bucket must be one of {sorted(_BUCKETS)}")
    return f"strftime(date_trunc('{bucket}', {col}), '%Y-%m-%d')"
```

`server/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import groups, overview, persons


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="relationships")
    app.state.db_path = db_path
    app.include_router(persons.router, prefix="/api")
    app.include_router(overview.router, prefix="/api")
    app.include_router(groups.router, prefix="/api")
    dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
```

`server/routes/persons.py`:

```python
from fastapi import APIRouter, Request

from ..db import run

router = APIRouter()

_LIST_SQL = """
    SELECT p.person_id, p.display_name,
           count(m.msg_id) AS total,
           count(m.msg_id) FILTER (WHERE m.is_from_me) AS sent,
           count(m.msg_id) FILTER (WHERE NOT m.is_from_me) AS received,
           min(m.ts_local) AS first_ts, max(m.ts_local) AS last_ts
    FROM persons p
    JOIN chat_members cm ON cm.person_id = p.person_id
    JOIN chats c ON c.chat_id = cm.chat_id AND NOT c.is_group
    JOIN messages m ON m.chat_id = c.chat_id
    GROUP BY 1, 2
    ORDER BY total DESC
"""


@router.get("/persons")
def list_persons(request: Request):
    return [
        {"person_id": r[0], "display_name": r[1], "total": r[2], "sent": r[3],
         "received": r[4], "first_ts": r[5], "last_ts": r[6]}
        for r in run(request.app.state.db_path, _LIST_SQL)
    ]
```

`server/routes/overview.py` and `server/routes/groups.py` (placeholders, filled in Tasks 11–12):

```python
from fastapi import APIRouter

router = APIRouter()
```

Create empty `server/__init__.py` and `server/routes/__init__.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_persons.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add server/ tests/conftest.py tests/test_api_persons.py
git commit -m "feat: FastAPI scaffolding + persons leaderboard endpoint"
```

---

### Task 11: Person & overview analytics endpoints

**Files:**
- Modify: `server/routes/persons.py` (append), `server/routes/overview.py` (replace placeholder)
- Create: `tests/test_api_overview.py`
- Modify: `tests/test_api_persons.py` (append tests)

**Interfaces:**
- Consumes: `run`, `bucket_expr` (Task 10), conftest dataset (Task 10).
- Produces:
  - `GET /api/overview/timeseries?bucket=` → `[{bucket, sent, received}]`, all messages including groups.
  - `GET /api/persons/{id}/timeseries?bucket=&include_groups=` → `[{bucket, sent, received}]` (1:1 only unless `include_groups=true`, which adds their group messages).
  - `GET /api/persons/{id}/stats` → `{person_id, display_name, total, sent, received, median_response_seconds_me, p90_response_seconds_me, median_response_seconds_them, p90_response_seconds_them, avg_chars_me, avg_chars_them, initiation_rate_me, top_emojis_me, top_emojis_them, tapbacks_from_them, tapbacks_from_me}` (emoji lists: `[{emoji, count}]`; tapback lists: `[{kind, count}]`); 404 for unknown person.
  - `GET /api/persons/{id}/heatmap` → `[{weekday, hour, count}]` (duckdb `dayofweek`: Sunday=0).
  - `GET /api/compare?ids=1,2&bucket=` → `[{person_id, display_name, series: [{bucket, total}]}]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_persons.py`:

```python
def _alice_id(client):
    return next(p["person_id"] for p in client.get("/api/persons").json()
                if p["display_name"] == "Alice Smith")


def test_person_timeseries_daily(client):
    pid = _alice_id(client)
    series = client.get(f"/api/persons/{pid}/timeseries?bucket=day").json()
    assert series == [
        {"bucket": "2024-06-01", "sent": 1, "received": 1},
        {"bucket": "2024-06-02", "sent": 1, "received": 1},
    ]


def test_person_timeseries_include_groups(client):
    pid = _alice_id(client)
    series = client.get(
        f"/api/persons/{pid}/timeseries?bucket=day&include_groups=true").json()
    assert series[0] == {"bucket": "2024-06-01", "sent": 1, "received": 2}


def test_person_stats(client):
    pid = _alice_id(client)
    s = client.get(f"/api/persons/{pid}/stats").json()
    assert s["display_name"] == "Alice Smith"
    assert s["median_response_seconds_me"] == 120.0
    assert s["median_response_seconds_them"] == 300.0
    assert s["initiation_rate_me"] == 0.5
    assert s["top_emojis_them"] == [{"emoji": "😂", "count": 1}]
    assert s["top_emojis_me"] == []
    assert s["tapbacks_from_them"] == [{"kind": "love", "count": 1}]
    assert s["tapbacks_from_me"] == []


def test_person_stats_404(client):
    assert client.get("/api/persons/9999/stats").status_code == 404


def test_person_heatmap(client):
    pid = _alice_id(client)
    cells = client.get(f"/api/persons/{pid}/heatmap").json()
    assert {"weekday": 6, "hour": 12, "count": 2} in cells   # Sat Jun 1
    assert {"weekday": 0, "hour": 9, "count": 2} in cells    # Sun Jun 2


def test_compare(client):
    people = client.get("/api/persons").json()
    ids = ",".join(str(p["person_id"]) for p in people)
    out = client.get(f"/api/compare?ids={ids}&bucket=month").json()
    totals = {o["display_name"]: o["series"][0]["total"] for o in out}
    assert totals == {"Alice Smith": 4, "Bob Jones": 1}
```

`tests/test_api_overview.py`:

```python
def test_overview_daily(client):
    series = client.get("/api/overview/timeseries?bucket=day").json()
    assert series == [
        {"bucket": "2024-06-01", "sent": 2, "received": 4},
        {"bucket": "2024-06-02", "sent": 1, "received": 1},
    ]


def test_invalid_bucket_rejected(client):
    assert client.get("/api/overview/timeseries?bucket=year; DROP").status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_persons.py tests/test_api_overview.py -v`
Expected: new tests FAIL with 404s (routes don't exist)

- [ ] **Step 3: Write the implementation**

Replace `server/routes/overview.py`:

```python
from fastapi import APIRouter, Request

from ..db import bucket_expr, run

router = APIRouter()


@router.get("/overview/timeseries")
def overview_timeseries(request: Request, bucket: str = "month"):
    sql = f"""
        SELECT {bucket_expr(bucket, col="ts_local")} AS bucket,
               count(*) FILTER (WHERE is_from_me) AS sent,
               count(*) FILTER (WHERE NOT is_from_me) AS received
        FROM messages GROUP BY 1 ORDER BY 1
    """
    return [{"bucket": r[0], "sent": r[1], "received": r[2]}
            for r in run(request.app.state.db_path, sql)]
```

Append to `server/routes/persons.py` (and add `HTTPException` to the fastapi import):

```python
_JOIN_1TO1 = """
    FROM messages m
    JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
    JOIN chat_members cm ON cm.chat_id = m.chat_id AND cm.person_id = ?
"""


@router.get("/persons/{person_id}/timeseries")
def person_timeseries(person_id: int, request: Request, bucket: str = "week",
                      include_groups: bool = False):
    group_filter = ("(NOT c.is_group OR m.person_id = cm.person_id)"
                    if include_groups else "NOT c.is_group")
    sql = f"""
        SELECT {bucket_expr(bucket)} AS bucket,
               count(*) FILTER (WHERE m.is_from_me) AS sent,
               count(*) FILTER (WHERE NOT m.is_from_me) AS received
        FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id
        JOIN chat_members cm ON cm.chat_id = m.chat_id AND cm.person_id = ?
        WHERE {group_filter}
        GROUP BY 1 ORDER BY 1
    """
    return [{"bucket": r[0], "sent": r[1], "received": r[2]}
            for r in run(request.app.state.db_path, sql, [person_id])]


@router.get("/persons/{person_id}/stats")
def person_stats(person_id: int, request: Request):
    db = request.app.state.db_path
    name = run(db, "SELECT display_name FROM persons WHERE person_id = ?", [person_id])
    if not name:
        raise HTTPException(status_code=404, detail="unknown person")
    core = run(db, f"""
        SELECT count(*),
               count(*) FILTER (WHERE m.is_from_me),
               count(*) FILTER (WHERE NOT m.is_from_me),
               median(m.response_seconds) FILTER (WHERE m.is_from_me),
               quantile_cont(m.response_seconds, 0.9) FILTER (WHERE m.is_from_me),
               median(m.response_seconds) FILTER (WHERE NOT m.is_from_me),
               quantile_cont(m.response_seconds, 0.9) FILTER (WHERE NOT m.is_from_me),
               avg(m.char_len) FILTER (WHERE m.is_from_me),
               avg(m.char_len) FILTER (WHERE NOT m.is_from_me)
        {_JOIN_1TO1}""", [person_id])[0]
    initiation = run(db, f"""
        WITH firsts AS (
            SELECT m.session_id, arg_min(m.is_from_me, m.ts_utc) AS starter_is_me
            {_JOIN_1TO1}
            GROUP BY 1)
        SELECT avg(CASE WHEN starter_is_me THEN 1.0 ELSE 0.0 END) FROM firsts
    """, [person_id])[0][0]

    def emojis(from_me: bool):
        return [{"emoji": r[0], "count": r[1]} for r in run(db, """
            SELECT e.emoji, count(*) AS c FROM emoji_uses e
            JOIN messages m ON m.msg_id = e.msg_id
            JOIN chats ch ON ch.chat_id = m.chat_id AND NOT ch.is_group
            JOIN chat_members cm ON cm.chat_id = m.chat_id AND cm.person_id = ?
            WHERE m.is_from_me = ? GROUP BY 1 ORDER BY c DESC LIMIT 10""",
            [person_id, from_me])]

    tap_from_them = [{"kind": r[0], "count": r[1]} for r in run(db,
        "SELECT kind, count(*) FROM tapbacks WHERE person_id = ? GROUP BY 1 ORDER BY 2 DESC",
        [person_id])]
    tap_from_me = [{"kind": r[0], "count": r[1]} for r in run(db, """
        SELECT t.kind, count(*) FROM tapbacks t
        JOIN messages m ON m.guid = t.target_guid
        WHERE t.is_from_me AND NOT m.is_from_me AND m.person_id = ?
        GROUP BY 1 ORDER BY 2 DESC""", [person_id])]

    return {
        "person_id": person_id, "display_name": name[0][0],
        "total": core[0], "sent": core[1], "received": core[2],
        "median_response_seconds_me": core[3], "p90_response_seconds_me": core[4],
        "median_response_seconds_them": core[5], "p90_response_seconds_them": core[6],
        "avg_chars_me": core[7], "avg_chars_them": core[8],
        "initiation_rate_me": initiation,
        "top_emojis_me": emojis(True), "top_emojis_them": emojis(False),
        "tapbacks_from_them": tap_from_them, "tapbacks_from_me": tap_from_me,
    }


@router.get("/persons/{person_id}/heatmap")
def person_heatmap(person_id: int, request: Request):
    sql = f"""
        SELECT dayofweek(m.ts_local) AS weekday, hour(m.ts_local) AS hour, count(*)
        {_JOIN_1TO1}
        GROUP BY 1, 2 ORDER BY 1, 2
    """
    return [{"weekday": r[0], "hour": r[1], "count": r[2]}
            for r in run(request.app.state.db_path, sql, [person_id])]


@router.get("/compare")
def compare(ids: str, request: Request, bucket: str = "month"):
    db = request.app.state.db_path
    out = []
    for pid in [int(x) for x in ids.split(",") if x.strip()]:
        name = run(db, "SELECT display_name FROM persons WHERE person_id = ?", [pid])
        if not name:
            continue
        series = run(db, f"""
            SELECT {bucket_expr(bucket)} AS bucket, count(*) AS total
            {_JOIN_1TO1}
            GROUP BY 1 ORDER BY 1""", [pid])
        out.append({"person_id": pid, "display_name": name[0][0],
                    "series": [{"bucket": r[0], "total": r[1]} for r in series]})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_persons.py tests/test_api_overview.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add server/routes/ tests/test_api_persons.py tests/test_api_overview.py
git commit -m "feat: overview + person analytics endpoints"
```

---

### Task 12: Group analytics endpoints

**Files:**
- Modify: `server/routes/groups.py` (replace placeholder)
- Create: `tests/test_api_groups.py`

**Interfaces:**
- Consumes: `run`, `bucket_expr` (Task 10), conftest dataset (Task 10).
- Produces:
  - `GET /api/groups` → `[{chat_id, name, participants, total, my_share, first_ts, last_ts}]` ordered by total desc. Unnamed groups display as `"Group <chat_id>"`.
  - `GET /api/groups/{id}/timeseries?bucket=` → `[{bucket, total, mine}]`.
  - `GET /api/groups/{id}/heatmap` → `[{weekday, hour, count}]`.
  - `GET /api/groups/{id}/stats` → `{chat_id, name, my_share, session_count, busiest_day: {date, count}, members: [{person_id, display_name, count, share, avg_chars, tapbacks_received}]}` where the caller's row has `person_id: null, display_name: "Me"`; 404 for unknown/non-group chat.

- [ ] **Step 1: Write the failing test**

`tests/test_api_groups.py`:

```python
import pytest


def _squad_id(client):
    return client.get("/api/groups").json()[0]["chat_id"]


def test_group_leaderboard(client):
    groups = client.get("/api/groups").json()
    assert len(groups) == 1
    g = groups[0]
    assert g["name"] == "the squad"
    assert g["participants"] == 2
    assert g["total"] == 3
    assert g["my_share"] == pytest.approx(1 / 3)


def test_group_timeseries(client):
    gid = _squad_id(client)
    series = client.get(f"/api/groups/{gid}/timeseries?bucket=day").json()
    assert series == [{"bucket": "2024-06-01", "total": 3, "mine": 1}]


def test_group_heatmap(client):
    gid = _squad_id(client)
    cells = client.get(f"/api/groups/{gid}/heatmap").json()
    assert cells == [{"weekday": 6, "hour": 13, "count": 3}]


def test_group_stats(client):
    gid = _squad_id(client)
    s = client.get(f"/api/groups/{gid}/stats").json()
    assert s["name"] == "the squad"
    assert s["my_share"] == pytest.approx(1 / 3)
    assert s["session_count"] == 1
    assert s["busiest_day"] == {"date": "2024-06-01", "count": 3}
    by_name = {m["display_name"]: m for m in s["members"]}
    assert set(by_name) == {"Alice Smith", "Bob Jones", "Me"}
    assert by_name["Me"]["person_id"] is None
    assert by_name["Me"]["count"] == 1
    assert by_name["Me"]["share"] == pytest.approx(1 / 3)
    assert by_name["Me"]["tapbacks_received"] == 1      # Bob laughed at g8
    assert by_name["Alice Smith"]["tapbacks_received"] == 0


def test_group_stats_404s(client):
    assert client.get("/api/groups/1/stats").status_code == 404      # 1:1 chat
    assert client.get("/api/groups/99999/stats").status_code == 404  # unknown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_groups.py -v`
Expected: FAIL — 404s / missing routes

- [ ] **Step 3: Write the implementation**

Replace `server/routes/groups.py`:

```python
from fastapi import APIRouter, HTTPException, Request

from ..db import bucket_expr, run

router = APIRouter()

_LIST_SQL = """
    SELECT c.chat_id,
           coalesce(nullif(c.name, ''), 'Group ' || c.chat_id) AS name,
           c.participant_count,
           count(m.msg_id) AS total,
           count(m.msg_id) FILTER (WHERE m.is_from_me)::DOUBLE
               / count(m.msg_id) AS my_share,
           min(m.ts_local) AS first_ts, max(m.ts_local) AS last_ts
    FROM chats c JOIN messages m ON m.chat_id = c.chat_id
    WHERE c.is_group
    GROUP BY 1, 2, 3
    ORDER BY total DESC
"""


def _require_group(db, chat_id: int) -> str:
    row = run(db, """SELECT coalesce(nullif(name, ''), 'Group ' || chat_id)
                     FROM chats WHERE chat_id = ? AND is_group""", [chat_id])
    if not row:
        raise HTTPException(status_code=404, detail="unknown group")
    return row[0][0]


@router.get("/groups")
def list_groups(request: Request):
    return [
        {"chat_id": r[0], "name": r[1], "participants": r[2], "total": r[3],
         "my_share": r[4], "first_ts": r[5], "last_ts": r[6]}
        for r in run(request.app.state.db_path, _LIST_SQL)
    ]


@router.get("/groups/{chat_id}/timeseries")
def group_timeseries(chat_id: int, request: Request, bucket: str = "week"):
    db = request.app.state.db_path
    _require_group(db, chat_id)
    sql = f"""
        SELECT {bucket_expr(bucket)} AS bucket, count(*) AS total,
               count(*) FILTER (WHERE m.is_from_me) AS mine
        FROM messages m WHERE m.chat_id = ?
        GROUP BY 1 ORDER BY 1
    """
    return [{"bucket": r[0], "total": r[1], "mine": r[2]}
            for r in run(db, sql, [chat_id])]


@router.get("/groups/{chat_id}/heatmap")
def group_heatmap(chat_id: int, request: Request):
    db = request.app.state.db_path
    _require_group(db, chat_id)
    sql = """
        SELECT dayofweek(ts_local) AS weekday, hour(ts_local) AS hour, count(*)
        FROM messages WHERE chat_id = ?
        GROUP BY 1, 2 ORDER BY 1, 2
    """
    return [{"weekday": r[0], "hour": r[1], "count": r[2]}
            for r in run(db, sql, [chat_id])]


@router.get("/groups/{chat_id}/stats")
def group_stats(chat_id: int, request: Request):
    db = request.app.state.db_path
    name = _require_group(db, chat_id)

    total = run(db, "SELECT count(*) FROM messages WHERE chat_id = ?", [chat_id])[0][0]
    member_rows = run(db, """
        SELECT p.person_id, p.display_name, count(*) AS cnt, avg(m.char_len)
        FROM messages m JOIN persons p ON p.person_id = m.person_id
        WHERE m.chat_id = ? AND NOT m.is_from_me
        GROUP BY 1, 2 ORDER BY cnt DESC""", [chat_id])
    me = run(db, """SELECT count(*), avg(char_len) FROM messages
                    WHERE chat_id = ? AND is_from_me""", [chat_id])[0]
    taps = dict(run(db, """
        SELECT coalesce(m.person_id, 0) AS pid, count(*)
        FROM tapbacks t JOIN messages m ON m.guid = t.target_guid
        WHERE m.chat_id = ? GROUP BY 1""", [chat_id]))
    busiest = run(db, """
        SELECT strftime(date_trunc('day', ts_local), '%Y-%m-%d') AS d, count(*) AS c
        FROM messages WHERE chat_id = ?
        GROUP BY 1 ORDER BY c DESC LIMIT 1""", [chat_id])
    sessions = run(db, "SELECT count(DISTINCT session_id) FROM messages WHERE chat_id = ?",
                   [chat_id])[0][0]

    members = [
        {"person_id": pid, "display_name": disp, "count": cnt,
         "share": cnt / total if total else 0.0, "avg_chars": avg,
         "tapbacks_received": taps.get(pid, 0)}
        for pid, disp, cnt, avg in member_rows
    ]
    if me[0]:
        members.append({"person_id": None, "display_name": "Me", "count": me[0],
                        "share": me[0] / total if total else 0.0, "avg_chars": me[1],
                        "tapbacks_received": taps.get(0, 0)})
    members.sort(key=lambda m: m["count"], reverse=True)

    return {
        "chat_id": chat_id, "name": name,
        "my_share": (me[0] / total) if total else 0.0,
        "session_count": sessions,
        "busiest_day": ({"date": busiest[0][0], "count": busiest[0][1]}
                        if busiest else None),
        "members": members,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api_groups.py -v`
Expected: all pass

- [ ] **Step 5: Run the whole Python suite**

Run: `uv run pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add server/routes/groups.py tests/test_api_groups.py
git commit -m "feat: group leaderboard, timeseries, heatmap, stats endpoints"
```

---

### Task 13: Web app scaffolding, API client, demo data, dev server

**Files:**
- Create: `web/` (Vite react-ts scaffold), `web/src/api.ts`, `web/src/lib/format.ts`, `web/src/lib/format.test.ts`, `web/src/lib/useFetch.ts`, `web/src/components/BucketPicker.tsx`, `web/src/App.tsx` (replace scaffold), `web/src/main.tsx` (replace), `web/src/index.css` (replace), `scripts/make_demo.py`, `server/__main__.py`
- Modify: `web/vite.config.ts` (dev proxy)

**Interfaces:**
- Produces: every exported type and fetcher in `web/src/api.ts` below (Tasks 14–16 import from it verbatim); `fmtDuration(seconds: number | null | undefined): string`, `fmtPercent(x: number | null | undefined): string`; `useFetch<T>(fn: () => Promise<T>, deps: unknown[]): T | null`; `BucketPicker({value, onChange})`; `python -m server [--db PATH --port N]` (binds 127.0.0.1 only); `uv run python scripts/make_demo.py` writes a synthetic `data/analytics.duckdb` so the dashboard can be built and verified **without** Full Disk Access.

- [ ] **Step 1: Scaffold the web app**

```bash
cd /Users/yaoderek/Desktop/relationships
npm create vite@latest web -- --template react-ts
cd web && npm install && npm install recharts react-router-dom && npm install -D vitest
```

Add to `web/package.json` scripts: `"test": "vitest run"`.

Replace `web/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
```

- [ ] **Step 2: Write the failing format tests**

`web/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { fmtDuration, fmtPercent } from "./format";

describe("fmtDuration", () => {
  it("scales units", () => {
    expect(fmtDuration(45)).toBe("45s");
    expect(fmtDuration(120)).toBe("2m");
    expect(fmtDuration(5400)).toBe("1.5h");
    expect(fmtDuration(172800)).toBe("2.0d");
    expect(fmtDuration(null)).toBe("—");
  });
});

describe("fmtPercent", () => {
  it("rounds", () => {
    expect(fmtPercent(0.335)).toBe("34%");
    expect(fmtPercent(null)).toBe("—");
  });
});
```

Run: `cd web && npx vitest run`
Expected: FAIL — `./format` not found

- [ ] **Step 3: Write format, api client, useFetch, BucketPicker**

`web/src/lib/format.ts`:

```ts
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export function fmtPercent(x: number | null | undefined): string {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}
```

`web/src/api.ts`:

```ts
export type Bucket = "day" | "week" | "month";
export type PersonSummary = {
  person_id: number; display_name: string; total: number;
  sent: number; received: number; first_ts: string; last_ts: string;
};
export type SeriesPoint = { bucket: string; sent: number; received: number };
export type HeatCell = { weekday: number; hour: number; count: number };
export type EmojiCount = { emoji: string; count: number };
export type TapbackCount = { kind: string; count: number };
export type PersonStats = {
  person_id: number; display_name: string; total: number; sent: number; received: number;
  median_response_seconds_me: number | null; p90_response_seconds_me: number | null;
  median_response_seconds_them: number | null; p90_response_seconds_them: number | null;
  avg_chars_me: number | null; avg_chars_them: number | null;
  initiation_rate_me: number | null;
  top_emojis_me: EmojiCount[]; top_emojis_them: EmojiCount[];
  tapbacks_from_them: TapbackCount[]; tapbacks_from_me: TapbackCount[];
};
export type CompareSeries = {
  person_id: number; display_name: string;
  series: { bucket: string; total: number }[];
};
export type GroupSummary = {
  chat_id: number; name: string; participants: number; total: number;
  my_share: number; first_ts: string; last_ts: string;
};
export type GroupSeriesPoint = { bucket: string; total: number; mine: number };
export type GroupMember = {
  person_id: number | null; display_name: string; count: number;
  share: number; avg_chars: number | null; tapbacks_received: number;
};
export type GroupStats = {
  chat_id: number; name: string; my_share: number; session_count: number;
  busiest_day: { date: string; count: number } | null; members: GroupMember[];
};

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export const fetchPersons = () => get<PersonSummary[]>("/api/persons");
export const fetchOverviewSeries = (bucket: Bucket) =>
  get<SeriesPoint[]>(`/api/overview/timeseries?bucket=${bucket}`);
export const fetchPersonSeries = (id: number, bucket: Bucket, includeGroups = false) =>
  get<SeriesPoint[]>(
    `/api/persons/${id}/timeseries?bucket=${bucket}&include_groups=${includeGroups}`);
export const fetchPersonStats = (id: number) =>
  get<PersonStats>(`/api/persons/${id}/stats`);
export const fetchPersonHeatmap = (id: number) =>
  get<HeatCell[]>(`/api/persons/${id}/heatmap`);
export const fetchCompare = (ids: number[], bucket: Bucket) =>
  get<CompareSeries[]>(`/api/compare?ids=${ids.join(",")}&bucket=${bucket}`);
export const fetchGroups = () => get<GroupSummary[]>("/api/groups");
export const fetchGroupSeries = (id: number, bucket: Bucket) =>
  get<GroupSeriesPoint[]>(`/api/groups/${id}/timeseries?bucket=${bucket}`);
export const fetchGroupHeatmap = (id: number) =>
  get<HeatCell[]>(`/api/groups/${id}/heatmap`);
export const fetchGroupStats = (id: number) => get<GroupStats>(`/api/groups/${id}/stats`);
```

`web/src/lib/useFetch.ts`:

```ts
import { useEffect, useState } from "react";

export function useFetch<T>(fn: () => Promise<T>, deps: unknown[]): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    fn().then((d) => { if (alive) setData(d); }).catch(console.error);
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return data;
}
```

`web/src/components/BucketPicker.tsx`:

```tsx
import type { Bucket } from "../api";

const BUCKETS: Bucket[] = ["day", "week", "month"];

export default function BucketPicker(
  { value, onChange }: { value: Bucket; onChange: (b: Bucket) => void },
) {
  return (
    <div style={{ display: "inline-flex", gap: 4 }}>
      {BUCKETS.map((b) => (
        <button key={b} onClick={() => onChange(b)}
                style={{ fontWeight: value === b ? 700 : 400 }}>
          {b}
        </button>
      ))}
    </div>
  );
}
```

Replace `web/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

Replace `web/src/App.tsx` (placeholder routes; Tasks 14–16 swap in real pages):

```tsx
import { Link, Route, Routes } from "react-router-dom";

export default function App() {
  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: 24 }}>
      <nav style={{ display: "flex", gap: 16, marginBottom: 24 }}>
        <Link to="/">Overview</Link>
        <Link to="/compare">Compare</Link>
        <Link to="/groups">Groups</Link>
      </nav>
      <Routes>
        <Route path="/" element={<p>Overview — Task 14</p>} />
        <Route path="/person/:id" element={<p>Person — Task 15</p>} />
        <Route path="/compare" element={<p>Compare — Task 15</p>} />
        <Route path="/groups" element={<p>Groups — Task 16</p>} />
        <Route path="/groups/:id" element={<p>Group detail — Task 16</p>} />
      </Routes>
    </div>
  );
}
```

Replace `web/src/index.css`; delete `web/src/App.css` and `web/src/assets/react.svg`, and remove their imports:

```css
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 0; }
a { color: inherit; }
button { cursor: pointer; }
h1 { font-size: 24px; }
h2 { font-size: 17px; margin-top: 28px; }
```

- [ ] **Step 4: Run format tests to verify they pass**

Run: `cd web && npx vitest run`
Expected: 1 test file (format.test.ts), all tests pass

- [ ] **Step 5: Add the demo-data script and dev server entrypoint**

`scripts/make_demo.py`:

```python
"""Synthetic demo analytics.duckdb — develop the dashboard without Full Disk Access."""
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.chatdb import read_raw
from ingest.handles import normalize_handle
from ingest.load import build_analytics_db
from tests.fixtures import apple_ns, make_chat_db

PEOPLE = [(1, "+15551230001", "Alice Demo"), (2, "+15551230002", "Bob Demo"),
          (3, "+15551230003", "Carol Demo")]
PHRASES = ["hey", "lol 😂", "sounds good", "omw", "nice 🎉", "ok ok",
           "what do you think?", "haha yes", "brutal 💀", "coffee?"]


def main() -> None:
    rng = random.Random(42)
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    chat_path = data_dir / "demo_chat.db"
    chat_path.unlink(missing_ok=True)

    handles = [(hid, num, "iMessage") for hid, num, _ in PEOPLE]
    chats = [(1, None, 45), (2, None, 45), (3, None, 45), (4, "the squad", 43)]
    chat_handles = [(1, 1), (2, 2), (3, 3), (4, 1), (4, 2), (4, 3)]

    messages, msg_id = [], 1
    start = datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc)
    for day in range(540):
        for chat_id, members, base in ((1, [1], 6), (2, [2], 3), (3, [3], 1), (4, [1, 2, 3], 4)):
            wave = max(0.0, 1 + 0.9 * math.sin(day / 60 + chat_id * 2))
            n = max(0, int(rng.gauss(base * wave, 1.5)))
            minute = 0
            for i in range(n):
                minute += rng.randint(1, 120)
                ts = start + timedelta(days=day, minutes=minute)
                from_me = (i % 2 == 0) if chat_id != 4 else rng.random() < 0.3
                messages.append({
                    "msg_id": msg_id, "guid": f"g{msg_id}",
                    "text": rng.choice(PHRASES),
                    "handle_id": 0 if from_me else rng.choice(members),
                    "chat_id": chat_id, "date": apple_ns(ts),
                    "is_from_me": int(from_me),
                })
                msg_id += 1

    make_chat_db(chat_path, handles, chats, chat_handles, messages)
    contacts = {normalize_handle(num): name for _, num, name in PEOPLE}
    build_analytics_db(data_dir / "analytics.duckdb", read_raw(chat_path), contacts)
    print(f"Wrote data/analytics.duckdb with {msg_id - 1} messages")


if __name__ == "__main__":
    main()
```

`server/__main__.py`:

```python
import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m server")
    p.add_argument("--db", type=Path, default=Path("data/analytics.duckdb"))
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    if not args.db.exists():
        raise SystemExit(f"{args.db} not found — run `python -m ingest` first "
                         "(or `python scripts/make_demo.py` for demo data)")
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify the dev loop end-to-end**

```bash
cd /Users/yaoderek/Desktop/relationships
uv run python scripts/make_demo.py        # → "Wrote data/analytics.duckdb with ~7000 messages"
uv run python -m server &                 # API on 127.0.0.1:8000
curl -s localhost:8000/api/persons | head -c 200   # JSON with Alice/Bob/Carol Demo
cd web && npm run dev                     # Vite on 5173, /api proxied
```

Open http://localhost:5173 — nav renders, placeholder routes work. Stop both servers.

- [ ] **Step 7: Commit**

```bash
git add web/ scripts/make_demo.py server/__main__.py
git commit -m "feat: web scaffolding, typed API client, demo data, server entrypoint"
```

---

### Task 14: Overview page (volume chart, relationship arcs, leaderboard)

**Files:**
- Create: `web/src/components/TimeSeries.tsx`, `web/src/components/ArcsChart.tsx`, `web/src/components/ArcsChart.test.ts`, `web/src/components/Leaderboard.tsx`, `web/src/pages/Overview.tsx`
- Modify: `web/src/App.tsx` (wire the route)

**Interfaces:**
- Consumes: `api.ts` fetchers/types, `useFetch`, `BucketPicker` (Task 13).
- Produces: `TimeSeries({data: SeriesPoint[]})`; `ArcsChart({data: CompareSeries[]})` + exported `mergeSeries(all: CompareSeries[]): Record<string, unknown>[]`; `Leaderboard({rows: LeaderboardRow[], onSelect})` with `LeaderboardRow = {key: number, name: string, total: number, subtitle: string}`. Tasks 15–16 reuse all three.

**NOTE:** Read the `dataviz` skill before writing these components; adjust the placeholder palette below to its guidance.

- [ ] **Step 1: Write the failing mergeSeries test**

`web/src/components/ArcsChart.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { mergeSeries } from "./ArcsChart";

describe("mergeSeries", () => {
  it("pivots person series into bucket rows, sorted", () => {
    const merged = mergeSeries([
      { person_id: 1, display_name: "A",
        series: [{ bucket: "2024-02", total: 3 }, { bucket: "2024-01", total: 1 }] },
      { person_id: 2, display_name: "B", series: [{ bucket: "2024-01", total: 5 }] },
    ]);
    expect(merged).toEqual([
      { bucket: "2024-01", A: 1, B: 5 },
      { bucket: "2024-02", A: 3 },
    ]);
  });
});
```

Run: `cd web && npx vitest run`
Expected: FAIL — `./ArcsChart` not found

- [ ] **Step 2: Write the components**

`web/src/components/TimeSeries.tsx`:

```tsx
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesPoint } from "../api";

export default function TimeSeries({ data }: { data: SeriesPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Area dataKey="received" stackId="1" name="Received"
              fill="#5B8FF9" stroke="#5B8FF9" fillOpacity={0.7} />
        <Area dataKey="sent" stackId="1" name="Sent"
              fill="#61DDAA" stroke="#61DDAA" fillOpacity={0.7} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

`web/src/components/ArcsChart.tsx`:

```tsx
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CompareSeries } from "../api";

const PALETTE = ["#5B8FF9", "#61DDAA", "#F6BD16", "#7262FD", "#78D3F8",
                 "#9661BC", "#F6903D", "#008685", "#F08BB4", "#65789B"];

export function mergeSeries(all: CompareSeries[]): Record<string, unknown>[] {
  const buckets = new Map<string, Record<string, unknown>>();
  for (const person of all) {
    for (const pt of person.series) {
      const row = buckets.get(pt.bucket) ?? { bucket: pt.bucket };
      row[person.display_name] = pt.total;
      buckets.set(pt.bucket, row);
    }
  }
  return [...buckets.values()]
    .sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
}

export default function ArcsChart({ data }: { data: CompareSeries[] }) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={mergeSeries(data)}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Legend />
        {data.map((p, i) => (
          <Line key={p.person_id} dataKey={p.display_name} dot={false}
                stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
```

`web/src/components/Leaderboard.tsx`:

```tsx
export type LeaderboardRow = { key: number; name: string; total: number; subtitle: string };

export default function Leaderboard(
  { rows, onSelect }: { rows: LeaderboardRow[]; onSelect: (key: number) => void },
) {
  const max = Math.max(1, ...rows.map((r) => r.total));
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.key} onClick={() => onSelect(r.key)} style={{ cursor: "pointer" }}>
            <td style={{ padding: "6px 8px", opacity: 0.5, width: 28 }}>{i + 1}</td>
            <td style={{ padding: "6px 8px" }}>
              <div>{r.name}</div>
              <div style={{ fontSize: 12, opacity: 0.6 }}>{r.subtitle}</div>
            </td>
            <td style={{ padding: "6px 8px", width: "40%" }}>
              <div style={{ background: "#5B8FF9", height: 8, borderRadius: 4,
                            width: `${(r.total / max) * 100}%` }} />
            </td>
            <td style={{ padding: "6px 8px", textAlign: "right",
                         fontVariantNumeric: "tabular-nums" }}>
              {r.total.toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`web/src/pages/Overview.tsx`:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCompare, fetchOverviewSeries, fetchPersons } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import ArcsChart from "../components/ArcsChart";
import Leaderboard from "../components/Leaderboard";
import TimeSeries from "../components/TimeSeries";
import { useFetch } from "../lib/useFetch";

export default function Overview() {
  const navigate = useNavigate();
  const [bucket, setBucket] = useState<Bucket>("month");
  const series = useFetch(() => fetchOverviewSeries(bucket), [bucket]);
  const persons = useFetch(fetchPersons, []);
  const topIds = (persons ?? []).slice(0, 10).map((p) => p.person_id).join(",");
  const arcs = useFetch(
    () => topIds ? fetchCompare(topIds.split(",").map(Number), "month")
                 : Promise.resolve([]),
    [topIds],
  );
  return (
    <>
      <h1>Overview</h1>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <TimeSeries data={series} />}
      <h2>Relationship arcs — top 10 people, monthly</h2>
      {arcs && arcs.length > 0 && <ArcsChart data={arcs} />}
      <h2>Top people (1:1 messages)</h2>
      {persons && (
        <Leaderboard
          rows={persons.slice(0, 25).map((p) => ({
            key: p.person_id, name: p.display_name, total: p.total,
            subtitle: `${p.first_ts.slice(0, 10)} → ${p.last_ts.slice(0, 10)}`,
          }))}
          onSelect={(id) => navigate(`/person/${id}`)}
        />
      )}
    </>
  );
}
```

In `web/src/App.tsx`, add `import Overview from "./pages/Overview";` and replace the `/` route:

```tsx
<Route path="/" element={<Overview />} />
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd web && npx vitest run`
Expected: format + mergeSeries tests pass

- [ ] **Step 4: Verify in the browser**

With demo data present: `uv run python -m server &` and `cd web && npm run dev`. Open http://localhost:5173 — stacked sent/received area chart, arcs chart with 3 demo people waxing/waning, clickable leaderboard (person route is still a Task-15 placeholder). Check the browser console for errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/
git commit -m "feat: overview page with volume chart, arcs, leaderboard"
```

---

### Task 15: Person detail + Compare pages

**Files:**
- Create: `web/src/components/Heatmap.tsx`, `web/src/components/StatGrid.tsx`, `web/src/pages/Person.tsx`, `web/src/pages/Compare.tsx`
- Modify: `web/src/App.tsx` (wire routes)

**Interfaces:**
- Consumes: Tasks 13–14 components/fetchers.
- Produces: `Heatmap({cells: HeatCell[]})` (7×24 CSS grid, weekday 0 = Sunday); `StatGrid({stats: PersonStats})` and named export `Stat({label, value})` (reused by Task 16).

- [ ] **Step 1: Write the components**

`web/src/components/Heatmap.tsx`:

```tsx
import { Fragment } from "react";
import type { HeatCell } from "../api";

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function Heatmap({ cells }: { cells: HeatCell[] }) {
  const lookup = new Map(cells.map((c) => [`${c.weekday}:${c.hour}`, c.count]));
  const max = Math.max(1, ...cells.map((c) => c.count));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "38px repeat(24, 1fr)", gap: 2 }}>
      <div />
      {Array.from({ length: 24 }, (_, h) => (
        <div key={h} style={{ fontSize: 9, textAlign: "center", opacity: 0.6 }}>
          {h % 6 === 0 ? h : ""}
        </div>
      ))}
      {DAYS.map((day, wd) => (
        <Fragment key={day}>
          <div style={{ fontSize: 11, opacity: 0.7, lineHeight: "16px" }}>{day}</div>
          {Array.from({ length: 24 }, (_, h) => {
            const count = lookup.get(`${wd}:${h}`) ?? 0;
            return (
              <div key={h} title={`${day} ${h}:00 — ${count} messages`}
                   style={{ height: 16, borderRadius: 3,
                            background: `rgba(91, 143, 249, ${count / max})`,
                            outline: "1px solid rgba(128,128,128,0.15)" }} />
            );
          })}
        </Fragment>
      ))}
    </div>
  );
}
```

`web/src/components/StatGrid.tsx`:

```tsx
import type { PersonStats } from "../api";
import { fmtDuration, fmtPercent } from "../lib/format";

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 12, border: "1px solid rgba(128,128,128,0.25)",
                  borderRadius: 8 }}>
      <div style={{ fontSize: 12, opacity: 0.6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

export const statGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
  gap: 8, margin: "16px 0",
} as const;

export default function StatGrid({ stats }: { stats: PersonStats }) {
  const fav = (xs: { emoji?: string; kind?: string; count: number }[]) =>
    xs.length ? `${xs[0].emoji ?? xs[0].kind} ×${xs[0].count}` : "—";
  return (
    <div style={statGridStyle}>
      <Stat label="Total messages" value={stats.total.toLocaleString()} />
      <Stat label="Sent / received"
            value={`${stats.sent.toLocaleString()} / ${stats.received.toLocaleString()}`} />
      <Stat label="You start convos" value={fmtPercent(stats.initiation_rate_me)} />
      <Stat label="Your reply time (median)"
            value={fmtDuration(stats.median_response_seconds_me)} />
      <Stat label="Their reply time (median)"
            value={fmtDuration(stats.median_response_seconds_them)} />
      <Stat label="Their favorite emoji" value={fav(stats.top_emojis_them)} />
      <Stat label="Their top tapback" value={fav(stats.tapbacks_from_them)} />
    </div>
  );
}
```

`web/src/pages/Person.tsx`:

```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchPersonHeatmap, fetchPersonSeries, fetchPersonStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import Heatmap from "../components/Heatmap";
import StatGrid from "../components/StatGrid";
import TimeSeries from "../components/TimeSeries";
import { useFetch } from "../lib/useFetch";

export default function Person() {
  const pid = Number(useParams().id);
  const [bucket, setBucket] = useState<Bucket>("week");
  const [includeGroups, setIncludeGroups] = useState(false);
  const stats = useFetch(() => fetchPersonStats(pid), [pid]);
  const series = useFetch(() => fetchPersonSeries(pid, bucket, includeGroups),
                          [pid, bucket, includeGroups]);
  const heatmap = useFetch(() => fetchPersonHeatmap(pid), [pid]);
  if (!stats) return <p>Loading…</p>;
  return (
    <>
      <h1>{stats.display_name}</h1>
      <StatGrid stats={stats} />
      <BucketPicker value={bucket} onChange={setBucket} />
      <label style={{ marginLeft: 12, fontSize: 13 }}>
        <input type="checkbox" checked={includeGroups}
               onChange={(e) => setIncludeGroups(e.target.checked)} />
        {" "}include group messages
      </label>
      {series && <TimeSeries data={series} />}
      <h2>When you talk</h2>
      {heatmap && <Heatmap cells={heatmap} />}
    </>
  );
}
```

`web/src/pages/Compare.tsx`:

```tsx
import { useState } from "react";
import { fetchCompare, fetchPersons } from "../api";
import type { Bucket } from "../api";
import ArcsChart from "../components/ArcsChart";
import BucketPicker from "../components/BucketPicker";
import { useFetch } from "../lib/useFetch";

export default function Compare() {
  const persons = useFetch(fetchPersons, []);
  const [selected, setSelected] = useState<number[]>([]);
  const [bucket, setBucket] = useState<Bucket>("month");
  const data = useFetch(
    () => selected.length ? fetchCompare(selected, bucket) : Promise.resolve([]),
    [selected.join(","), bucket],
  );
  const toggle = (id: number) =>
    setSelected((s) => s.includes(id) ? s.filter((x) => x !== id)
                       : s.length < 5 ? [...s, id] : s);
  return (
    <>
      <h1>Compare (pick up to 5)</h1>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
        {(persons ?? []).slice(0, 30).map((p) => (
          <button key={p.person_id} onClick={() => toggle(p.person_id)}
                  style={{ fontWeight: selected.includes(p.person_id) ? 700 : 400 }}>
            {p.display_name}
          </button>
        ))}
      </div>
      <BucketPicker value={bucket} onChange={setBucket} />
      {data && data.length > 0 && <ArcsChart data={data} />}
    </>
  );
}
```

In `web/src/App.tsx`, add imports for `Person` and `Compare` and replace their routes:

```tsx
<Route path="/person/:id" element={<Person />} />
<Route path="/compare" element={<Compare />} />
```

- [ ] **Step 2: Verify tests still pass and pages render**

Run: `cd web && npx vitest run` — all pass.
Browser (demo data, both servers running): click a person on Overview → stat cards show reply times/initiation; toggle "include group messages" changes the series; heatmap shows morning-heavy demo pattern. Compare: pick 2–3 demo people → overlaid lines.

- [ ] **Step 3: Commit**

```bash
git add web/src/
git commit -m "feat: person detail and compare pages"
```

---

### Task 16: Group pages (leaderboard, detail with share-of-voice)

**Files:**
- Create: `web/src/components/GroupTimeSeries.tsx`, `web/src/pages/Groups.tsx`, `web/src/pages/GroupDetail.tsx`
- Modify: `web/src/App.tsx` (wire routes)

**Interfaces:**
- Consumes: `fetchGroups`, `fetchGroupSeries`, `fetchGroupHeatmap`, `fetchGroupStats` (Task 13); `Leaderboard` (Task 14); `Heatmap`, `Stat`, `statGridStyle` (Task 15).

- [ ] **Step 1: Write the components and pages**

`web/src/components/GroupTimeSeries.tsx`:

```tsx
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { GroupSeriesPoint } from "../api";

export default function GroupTimeSeries({ data }: { data: GroupSeriesPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <CartesianGrid strokeOpacity={0.15} vertical={false} />
        <XAxis dataKey="bucket" tickLine={false} minTickGap={40} />
        <YAxis tickLine={false} axisLine={false} width={44} />
        <Tooltip />
        <Legend />
        <Line dataKey="total" name="All messages" dot={false}
              stroke="#5B8FF9" strokeWidth={2} />
        <Line dataKey="mine" name="Mine" dot={false}
              stroke="#61DDAA" strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

`web/src/pages/Groups.tsx`:

```tsx
import { useNavigate } from "react-router-dom";
import { fetchGroups } from "../api";
import Leaderboard from "../components/Leaderboard";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

export default function Groups() {
  const groups = useFetch(fetchGroups, []);
  const navigate = useNavigate();
  return (
    <>
      <h1>Group chats</h1>
      {groups && (
        <Leaderboard
          rows={groups.map((g) => ({
            key: g.chat_id, name: g.name, total: g.total,
            subtitle: `${g.participants} people · you: ${fmtPercent(g.my_share)}`,
          }))}
          onSelect={(id) => navigate(`/groups/${id}`)}
        />
      )}
    </>
  );
}
```

`web/src/pages/GroupDetail.tsx`:

```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchGroupHeatmap, fetchGroupSeries, fetchGroupStats } from "../api";
import type { Bucket } from "../api";
import BucketPicker from "../components/BucketPicker";
import GroupTimeSeries from "../components/GroupTimeSeries";
import Heatmap from "../components/Heatmap";
import Leaderboard from "../components/Leaderboard";
import { Stat, statGridStyle } from "../components/StatGrid";
import { fmtPercent } from "../lib/format";
import { useFetch } from "../lib/useFetch";

export default function GroupDetail() {
  const gid = Number(useParams().id);
  const [bucket, setBucket] = useState<Bucket>("week");
  const stats = useFetch(() => fetchGroupStats(gid), [gid]);
  const series = useFetch(() => fetchGroupSeries(gid, bucket), [gid, bucket]);
  const heatmap = useFetch(() => fetchGroupHeatmap(gid), [gid]);
  if (!stats) return <p>Loading…</p>;
  return (
    <>
      <h1>{stats.name}</h1>
      <div style={statGridStyle}>
        <Stat label="Your share" value={fmtPercent(stats.my_share)} />
        <Stat label="Sessions" value={stats.session_count.toLocaleString()} />
        {stats.busiest_day && (
          <Stat label="Busiest day"
                value={`${stats.busiest_day.date} (${stats.busiest_day.count})`} />
        )}
      </div>
      <BucketPicker value={bucket} onChange={setBucket} />
      {series && <GroupTimeSeries data={series} />}
      <h2>Share of voice</h2>
      <Leaderboard
        rows={stats.members.map((m, i) => ({
          key: m.person_id ?? -1 - i, name: m.display_name, total: m.count,
          subtitle: `${fmtPercent(m.share)} · ${m.tapbacks_received} tapbacks · `
            + `avg ${Math.round(m.avg_chars ?? 0)} chars`,
        }))}
        onSelect={() => {}}
      />
      <h2>When it's active</h2>
      {heatmap && <Heatmap cells={heatmap} />}
    </>
  );
}
```

In `web/src/App.tsx`, add imports for `Groups` and `GroupDetail` and replace their routes:

```tsx
<Route path="/groups" element={<Groups />} />
<Route path="/groups/:id" element={<GroupDetail />} />
```

- [ ] **Step 2: Verify**

Run: `cd web && npx vitest run` — all pass.
Browser: Groups tab → "the squad" in leaderboard with your-share subtitle → detail page shows trendline (total vs mine), share-of-voice leaderboard with Me/Alice/Bob/Carol rows, heatmap.

- [ ] **Step 3: Commit**

```bash
git add web/src/
git commit -m "feat: group leaderboard and detail pages"
```

---

### Task 17: Production serving, README, full verification

**Files:**
- Create: `README.md`
- No code changes: `server/app.py` already mounts `web/dist` when present (Task 10).

- [ ] **Step 1: Build the frontend and verify single-command serving**

```bash
cd /Users/yaoderek/Desktop/relationships/web && npm run build
cd .. && uv run python -m server &
curl -s -o /dev/null -w "%{http_code}" localhost:8000/          # 200 (index.html)
curl -s localhost:8000/api/groups | head -c 200                 # JSON
```

Open http://localhost:8000 directly — the full dashboard works without the Vite dev server. Stop the server.

- [ ] **Step 2: Write README.md**

````markdown
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
````

- [ ] **Step 3: Run everything one last time**

```bash
uv run pytest -q                 # all pass
cd web && npx vitest run && npm run build && cd ..   # all pass, build clean
```

- [ ] **Step 4: (If Full Disk Access is granted) first real ingest**

```bash
uv run python -m ingest          # prints "Ingested N messages from M chats"
uv run python -m server          # browse your real data at 127.0.0.1:8000
```

If FDA is missing this fails with the setup instructions — that's the expected UX, not a bug. Spot-check: your top people look right; response-time medians are plausible (seconds–hours, not days); an unmatched raw number appearing high in the leaderboard means an AddressBook miss → add it to `overrides.yaml`.

- [ ] **Step 5: Commit**

```bash
git add README.md web/
git commit -m "feat: production serving verified + README"
```

---

## Plan Self-Review Notes

- **Spec coverage:** ingest pipeline (Tasks 1–9), data model incl. `emoji_uses` beyond spec's list (supports the spec's "emoji favorites" stat), API endpoints incl. all four group endpoints (Tasks 10–12), dashboard Overview/Person/Compare/Groups (Tasks 13–16), single-command serving + FDA error UX (Tasks 9, 17), privacy constraints in Global Constraints. Spec's "message-length trend" is covered as `avg_chars` stats; per-bucket length trend is a trivial later addition to the timeseries SQL if wanted.
- **Type consistency:** API response shapes in Tasks 10–12 match `web/src/api.ts` types in Task 13 field-for-field; `dayofweek` Sunday=0 convention matches `Heatmap.tsx` DAYS ordering; tapback kinds are the Task 7 `TAPBACK_KINDS` values end-to-end.
- **Known simplifications (deliberate):** 1:1 chats with 2+ handle members (rare merged-SIM edge case) get no outgoing attribution (counterpart map requires exactly 1 member); `include_groups` adds only *their* group messages by design (§group-chat judgment call).

