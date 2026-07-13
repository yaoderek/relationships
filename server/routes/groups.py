from fastapi import APIRouter, HTTPException, Request

from ..db import bucket_expr, run
from ..stopwords import STOPWORDS as _STOPWORDS

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
    WHERE c.is_group {msg_filter}
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
def list_groups(request: Request, days: int | None = None):
    sql = _LIST_SQL.format(
        msg_filter="AND m.ts_local >= current_timestamp - INTERVAL 1 DAY * ?"
                   if days else "")
    return [
        {"chat_id": r[0], "name": r[1], "participants": r[2], "total": r[3],
         "my_share": r[4], "first_ts": r[5], "last_ts": r[6]}
        for r in run(request.app.state.db_path, sql, [days] if days else [])
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


def _member_filter(person_id: int) -> tuple[str, list]:
    # person_id 0 means the account owner ("Me"); my rows carry no person_id.
    if person_id == 0:
        return "m.is_from_me", []
    return "m.person_id = ? AND NOT m.is_from_me", [person_id]


def _require_member(db, chat_id: int, person_id: int) -> str:
    if person_id == 0:
        return "You"
    row = run(db, """
        SELECT p.display_name FROM chat_members cm
        JOIN persons p ON p.person_id = cm.person_id
        WHERE cm.chat_id = ? AND cm.person_id = ?""", [chat_id, person_id])
    if not row:
        raise HTTPException(status_code=404, detail="not a member of this group")
    return row[0][0]


@router.get("/groups/{chat_id}/members/{person_id}/stats")
def group_member_stats(chat_id: int, person_id: int, request: Request):
    db = request.app.state.db_path
    _require_group(db, chat_id)
    display_name = _require_member(db, chat_id, person_id)
    cond, params = _member_filter(person_id)

    total = run(db, "SELECT count(*) FROM messages WHERE chat_id = ?", [chat_id])[0][0]
    core = run(db, f"""
        SELECT count(*), avg(m.char_len)
        FROM messages m WHERE m.chat_id = ? AND {cond}""", [chat_id, *params])[0]
    sessions = run(db, f"""
        SELECT count(DISTINCT m.session_id),
               count(DISTINCT m.session_id) FILTER (WHERE {cond})
        FROM messages m WHERE m.chat_id = ?""", [*params, chat_id])[0]
    ended = run(db, f"""
        WITH lasts AS (
            SELECT m.session_id,
                   arg_max(CASE WHEN {cond} THEN 1 ELSE 0 END, m.ts_utc) AS by_member
            FROM messages m WHERE m.chat_id = ?
            GROUP BY 1)
        SELECT coalesce(sum(by_member), 0) FROM lasts""", [*params, chat_id])[0][0]
    placeholders = ", ".join("?" for _ in _STOPWORDS)
    top_words = run(db, f"""
        SELECT w AS word, count(*) AS c FROM (
            SELECT unnest(string_split_regex(lower(m.text), '[^a-z'']+')) AS w
            FROM messages m
            WHERE m.chat_id = ? AND {cond} AND m.text IS NOT NULL)
        WHERE len(w) >= 3 AND w NOT IN ({placeholders})
        GROUP BY 1 ORDER BY c DESC, w LIMIT 10""",
        [chat_id, *params, *_STOPWORDS])
    top_emojis = run(db, f"""
        SELECT e.emoji, count(*) AS c FROM emoji_uses e
        JOIN messages m ON m.msg_id = e.msg_id
        WHERE m.chat_id = ? AND {cond}
        GROUP BY 1 ORDER BY c DESC LIMIT 5""", [chat_id, *params])
    tap_cond = "t.is_from_me" if person_id == 0 else "t.person_id = ? AND NOT t.is_from_me"
    tap_params = [] if person_id == 0 else [person_id]
    reactions_given = run(db, f"""
        SELECT t.kind, count(*) AS c FROM tapbacks t
        JOIN messages tgt ON tgt.guid = t.target_guid
        WHERE tgt.chat_id = ? AND {tap_cond}
        GROUP BY 1 ORDER BY c DESC""", [chat_id, *tap_params])
    tapbacks_received = run(db, f"""
        SELECT count(*) FROM tapbacks t
        JOIN messages m ON m.guid = t.target_guid
        WHERE m.chat_id = ? AND {cond}""", [chat_id, *params])[0][0]

    return {
        "chat_id": chat_id, "person_id": person_id, "display_name": display_name,
        "count": core[0], "share": core[0] / total if total else 0.0,
        "avg_chars": core[1],
        "sessions_total": sessions[0], "sessions_participated": sessions[1],
        "sessions_ghosted": sessions[0] - sessions[1], "sessions_ended": ended,
        "top_words": [{"word": r[0], "count": r[1]} for r in top_words],
        "top_emojis": [{"emoji": r[0], "count": r[1]} for r in top_emojis],
        "top_reactions_given": [{"kind": r[0], "count": r[1]} for r in reactions_given],
        "tapbacks_received": tapbacks_received,
    }


@router.get("/groups/{chat_id}/members/{person_id}/timeseries")
def group_member_timeseries(chat_id: int, person_id: int, request: Request,
                            bucket: str = "week"):
    db = request.app.state.db_path
    _require_group(db, chat_id)
    _require_member(db, chat_id, person_id)
    cond, params = _member_filter(person_id)
    sql = f"""
        SELECT {bucket_expr(bucket)} AS bucket, count(*) AS count
        FROM messages m WHERE m.chat_id = ? AND {cond}
        GROUP BY 1 ORDER BY 1
    """
    return [{"bucket": r[0], "count": r[1]}
            for r in run(db, sql, [chat_id, *params])]


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
        members.append({"person_id": None, "display_name": "You", "count": me[0],
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
