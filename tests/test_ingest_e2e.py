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
