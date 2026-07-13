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
    attachment_msg_ids = {a["msg_id"] for a in raw.attachments}

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
            "has_attachment": bool(m["cache_has_attachments"]) or m["msg_id"] in attachment_msg_ids,
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
    if raw.attachments:
        con.executemany("INSERT INTO attachments VALUES (?,?,?)",
                        [(a["msg_id"], a["mime_type"], a["total_bytes"])
                         for a in raw.attachments])
    if emoji_rows:
        con.executemany("INSERT INTO emoji_uses VALUES (?,?)", emoji_rows)
    con.close()
