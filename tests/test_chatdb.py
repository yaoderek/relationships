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
