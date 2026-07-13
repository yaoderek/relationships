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
