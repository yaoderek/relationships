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
