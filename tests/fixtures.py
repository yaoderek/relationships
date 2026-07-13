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
