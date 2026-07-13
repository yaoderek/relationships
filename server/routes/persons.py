from fastapi import APIRouter, HTTPException, Request

from ..db import bucket_expr, run

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
