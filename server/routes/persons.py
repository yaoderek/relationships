import re

from fastapi import APIRouter, HTTPException, Request

from ..db import bucket_expr, run
from ..llm import summarize_day
from ..stopwords import STOPWORDS

router = APIRouter()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_LIST_SQL = """
    WITH msgs AS (
        SELECT cm.person_id, m.chat_id, m.session_id, m.ts_utc, m.ts_local,
               m.is_from_me, m.response_seconds
        FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
        JOIN chat_members cm ON cm.chat_id = m.chat_id
        {msg_filter}
    ),
    base AS (
        SELECT person_id,
               count(*) AS total,
               count(*) FILTER (WHERE is_from_me) AS sent,
               count(*) FILTER (WHERE NOT is_from_me) AS received,
               min(ts_local) AS first_ts, max(ts_local) AS last_ts,
               median(response_seconds) FILTER (WHERE is_from_me) AS median_me,
               median(response_seconds) FILTER (WHERE NOT is_from_me) AS median_them
        FROM msgs GROUP BY 1
    ),
    sess AS (
        SELECT person_id, session_id, count(*) AS n,
               date_diff('second', min(ts_utc), max(ts_utc)) AS dur,
               arg_min(is_from_me, ts_utc) AS first_from_me,
               arg_max(is_from_me, ts_utc) AS last_from_me
        FROM msgs GROUP BY 1, 2
    ),
    sess_agg AS (
        SELECT person_id,
               avg(CASE WHEN first_from_me THEN 1.0 ELSE 0.0 END) AS initiation,
               avg(n) AS avg_session_messages,
               avg(dur) AS avg_session_seconds,
               count(*) FILTER (WHERE last_from_me) AS ghosts_by_them,
               count(*) FILTER (WHERE NOT last_from_me) AS ghosts_by_me
        FROM sess GROUP BY 1
    ),
    flagged AS (
        SELECT person_id, chat_id, ts_utc, is_from_me,
               CASE WHEN lag(is_from_me) OVER w = is_from_me
                         AND lag(session_id) OVER w = session_id
                    THEN 0 ELSE 1 END AS new_block,
               CASE WHEN lag(is_from_me) OVER w = is_from_me
                         AND date_diff('second', lag(ts_utc) OVER w, ts_utc) >= 600
                    THEN 1 ELSE 0 END AS double_text
        FROM msgs
        WINDOW w AS (PARTITION BY chat_id ORDER BY ts_utc)
    ),
    block_sizes AS (
        SELECT person_id, any_value(is_from_me) AS is_from_me, count(*) AS n
        FROM (SELECT *, sum(new_block) OVER (PARTITION BY chat_id ORDER BY ts_utc)
                     AS block_id
              FROM flagged)
        GROUP BY person_id, chat_id, block_id
    ),
    block_agg AS (
        SELECT person_id,
               avg(n) FILTER (WHERE is_from_me) AS block_me,
               avg(n) FILTER (WHERE NOT is_from_me) AS block_them
        FROM block_sizes GROUP BY 1
    ),
    dt_agg AS (
        SELECT person_id,
               count(*) FILTER (WHERE double_text = 1 AND is_from_me) AS dt_me,
               count(*) FILTER (WHERE double_text = 1 AND NOT is_from_me) AS dt_them
        FROM flagged GROUP BY 1
    ),
    streaks AS (
        SELECT person_id, count(*) AS streak_days
        FROM (
            SELECT person_id, d,
                   max(d) OVER (PARTITION BY person_id) AS max_d,
                   row_number() OVER (PARTITION BY person_id ORDER BY d DESC) AS rn
            FROM (SELECT DISTINCT person_id, date_trunc('day', ts_local) AS d
                  FROM msgs)
        )
        WHERE d = max_d - INTERVAL 1 DAY * (rn - 1)
          AND max_d >= current_date - INTERVAL 1 DAY
        GROUP BY 1
    )
    SELECT p.person_id, p.display_name,
           b.total, b.sent, b.received, b.first_ts, b.last_ts,
           b.median_me, b.median_them,
           s.initiation, s.avg_session_messages, s.avg_session_seconds,
           s.ghosts_by_them, s.ghosts_by_me,
           bl.block_me, bl.block_them,
           d.dt_me, d.dt_them,
           coalesce(st.streak_days, 0) AS streak_days
    FROM persons p
    JOIN base b ON b.person_id = p.person_id
    JOIN sess_agg s ON s.person_id = p.person_id
    JOIN block_agg bl ON bl.person_id = p.person_id
    JOIN dt_agg d ON d.person_id = p.person_id
    LEFT JOIN streaks st ON st.person_id = p.person_id
    WHERE p.display_name NOT LIKE 'urn:%'
    ORDER BY b.total DESC
"""


@router.get("/persons")
def list_persons(request: Request, days: int | None = None):
    sql = _LIST_SQL.format(
        msg_filter="WHERE m.ts_local >= current_timestamp - INTERVAL 1 DAY * ?"
                   if days else "")
    return [
        {"person_id": r[0], "display_name": r[1], "total": r[2], "sent": r[3],
         "received": r[4], "first_ts": r[5], "last_ts": r[6],
         "median_response_seconds_me": r[7], "median_response_seconds_them": r[8],
         "initiation_rate_me": r[9], "avg_session_messages": r[10],
         "avg_session_seconds": r[11], "ghosts_by_them": r[12],
         "ghosts_by_me": r[13], "avg_reply_block_me": r[14],
         "avg_reply_block_them": r[15], "double_texts_me": r[16],
         "double_texts_them": r[17], "streak_days": r[18]}
        for r in run(request.app.state.db_path, sql, [days] if days else [])
    ]


_JOIN_1TO1 = """
    FROM messages m
    JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
    JOIN chat_members cm ON cm.chat_id = m.chat_id AND cm.person_id = ?
"""


@router.get("/persons/timeline")
def persons_timeline(request: Request, top: int = 40):
    sql = """
        WITH totals AS (
            SELECT cm.person_id, count(*) AS total
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            JOIN chat_members cm ON cm.chat_id = m.chat_id
            GROUP BY 1 ORDER BY total DESC LIMIT ?
        )
        SELECT strftime(date_trunc('month', m.ts_local), '%Y-%m') AS bucket,
               p.person_id, p.display_name, count(*) AS c
        FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
        JOIN chat_members cm ON cm.chat_id = m.chat_id
        JOIN totals t ON t.person_id = cm.person_id
        JOIN persons p ON p.person_id = cm.person_id
        WHERE p.display_name NOT LIKE 'urn:%'
        GROUP BY 1, 2, 3
        ORDER BY 1, 4 DESC
    """
    return [{"bucket": r[0], "person_id": r[1], "display_name": r[2],
             "count": r[3]}
            for r in run(request.app.state.db_path, sql, [top])]


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

    # Reply blocks = maximal runs of consecutive messages from the same sender
    # within a session. Double text = same sender again after >= 10 unanswered min.
    blocks = run(db, f"""
        WITH msgs AS (
            SELECT m.chat_id, m.session_id, m.ts_utc, m.is_from_me
            {_JOIN_1TO1}
        ),
        flagged AS (
            SELECT *,
                   CASE WHEN lag(is_from_me) OVER w = is_from_me
                             AND lag(session_id) OVER w = session_id
                        THEN 0 ELSE 1 END AS new_block,
                   CASE WHEN lag(chat_id) OVER w = chat_id
                             AND lag(is_from_me) OVER w = is_from_me
                             AND date_diff('second', lag(ts_utc) OVER w, ts_utc) >= 600
                        THEN 1 ELSE 0 END AS double_text
            FROM msgs
            WINDOW w AS (ORDER BY chat_id, ts_utc)
        ),
        block_sizes AS (
            SELECT any_value(is_from_me) AS is_from_me, count(*) AS n
            FROM (SELECT *, sum(new_block) OVER (ORDER BY chat_id, ts_utc) AS block_id
                  FROM flagged)
            GROUP BY block_id
        )
        SELECT (SELECT avg(n) FROM block_sizes WHERE is_from_me),
               (SELECT avg(n) FROM block_sizes WHERE NOT is_from_me),
               (SELECT count(*) FROM flagged WHERE double_text = 1 AND is_from_me),
               (SELECT count(*) FROM flagged WHERE double_text = 1 AND NOT is_from_me)
    """, [person_id])[0]
    sessions = run(db, f"""
        WITH sess AS (
            SELECT m.session_id, count(*) AS n,
                   date_diff('second', min(m.ts_utc), max(m.ts_utc)) AS dur,
                   arg_max(m.is_from_me, m.ts_utc) AS last_from_me
            {_JOIN_1TO1}
            GROUP BY 1)
        SELECT avg(n), avg(dur),
               count(*) FILTER (WHERE last_from_me),
               count(*) FILTER (WHERE NOT last_from_me)
        FROM sess""", [person_id])[0]
    block_me, block_them, doubles_me, doubles_them = blocks
    block_ratio = (block_them / block_me) if block_me and block_them else None

    def words(from_me: bool):
        placeholders = ", ".join("?" for _ in STOPWORDS)
        return [{"word": r[0], "count": r[1]} for r in run(db, f"""
            SELECT w AS word, count(*) AS c FROM (
                SELECT unnest(string_split_regex(
                    replace(lower(m.text), '’', ''''), '[^a-z'']+')) AS w
                {_JOIN_1TO1}
                WHERE m.is_from_me = ? AND m.text IS NOT NULL)
            WHERE len(w) >= 3 AND w NOT IN ({placeholders})
            GROUP BY 1 ORDER BY c DESC, w LIMIT 10""",
            [person_id, from_me, *STOPWORDS])]

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
        "avg_reply_block_me": block_me, "avg_reply_block_them": block_them,
        "reply_block_ratio": block_ratio,
        "double_texts_me": doubles_me, "double_texts_them": doubles_them,
        "ghosts_by_them": sessions[2], "ghosts_by_me": sessions[3],
        "avg_session_messages": sessions[0], "avg_session_seconds": sessions[1],
        "top_words_me": words(True), "top_words_them": words(False),
        "top_emojis_me": emojis(True), "top_emojis_them": emojis(False),
        "tapbacks_from_them": tap_from_them, "tapbacks_from_me": tap_from_me,
    }


@router.get("/persons/{person_id}/trends")
def person_trends(person_id: int, request: Request, bucket: str = "month"):
    db = request.app.state.db_path
    b = bucket_expr(bucket, col="ts_local")

    # Reply-time medians are noisy per bucket, so smooth them with a trailing
    # 4-bucket rolling average (which also bridges empty buckets).
    base = run(db, f"""
        WITH msgs AS (SELECT m.* {_JOIN_1TO1}),
        by_bucket AS (
            SELECT {b} AS bucket,
                   count(*) FILTER (WHERE is_from_me) AS sent,
                   count(*) FILTER (WHERE NOT is_from_me) AS received,
                   median(response_seconds) FILTER (WHERE is_from_me) AS reply_me,
                   median(response_seconds) FILTER (WHERE NOT is_from_me) AS reply_them
            FROM msgs GROUP BY 1
        )
        SELECT bucket, sent, received,
               avg(reply_me) OVER (ORDER BY bucket
                                   ROWS BETWEEN 3 PRECEDING AND CURRENT ROW),
               avg(reply_them) OVER (ORDER BY bucket
                                     ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
        FROM by_bucket""", [person_id])

    blocks = run(db, f"""
        WITH msgs AS (
            SELECT m.chat_id, m.session_id, m.ts_utc, m.ts_local, m.is_from_me
            {_JOIN_1TO1}
        ),
        flagged AS (
            SELECT *,
                   CASE WHEN lag(is_from_me) OVER w = is_from_me
                             AND lag(session_id) OVER w = session_id
                        THEN 0 ELSE 1 END AS new_block,
                   CASE WHEN lag(is_from_me) OVER w = is_from_me
                             AND date_diff('second', lag(ts_utc) OVER w, ts_utc) >= 600
                        THEN 1 ELSE 0 END AS double_text
            FROM msgs
            WINDOW w AS (PARTITION BY chat_id ORDER BY ts_utc)
        ),
        block_sizes AS (
            SELECT any_value(is_from_me) AS is_from_me, count(*) AS n,
                   min(ts_local) AS t0
            FROM (SELECT *, sum(new_block) OVER (PARTITION BY chat_id ORDER BY ts_utc)
                         AS block_id
                  FROM flagged)
            GROUP BY chat_id, block_id
        ),
        block_by_bucket AS (
            SELECT {bucket_expr(bucket, col="t0")} AS bucket,
                   avg(n) FILTER (WHERE is_from_me) AS block_me,
                   avg(n) FILTER (WHERE NOT is_from_me) AS block_them
            FROM block_sizes GROUP BY 1
        ),
        dt_by_bucket AS (
            SELECT {b} AS bucket,
                   count(*) FILTER (WHERE double_text = 1 AND is_from_me) AS dt_me,
                   count(*) FILTER (WHERE double_text = 1 AND NOT is_from_me) AS dt_them
            FROM flagged GROUP BY 1
        )
        SELECT coalesce(bb.bucket, db.bucket), bb.block_me, bb.block_them,
               db.dt_me, db.dt_them
        FROM block_by_bucket bb FULL JOIN dt_by_bucket db ON db.bucket = bb.bucket
        """, [person_id])

    sessions = run(db, f"""
        WITH sess AS (
            SELECT m.session_id, min(m.ts_local) AS t0,
                   arg_min(m.is_from_me, m.ts_utc) AS first_from_me
            {_JOIN_1TO1}
            GROUP BY 1)
        SELECT {bucket_expr(bucket, col="t0")} AS bucket,
               avg(CASE WHEN first_from_me THEN 1.0 ELSE 0.0 END) AS initiation
        FROM sess GROUP BY 1""", [person_id])

    out: dict[str, dict] = {}
    for r in base:
        out[r[0]] = {"bucket": r[0], "sent": r[1], "received": r[2],
                     "median_reply_me": r[3], "median_reply_them": r[4],
                     "texts_per_reply_me": None, "texts_per_reply_them": None,
                     "double_texts_me": 0, "double_texts_them": 0,
                     "initiation_me": None}
    for r in blocks:
        row = out.setdefault(r[0], {"bucket": r[0], "sent": 0, "received": 0,
                                    "median_reply_me": None,
                                    "median_reply_them": None,
                                    "initiation_me": None})
        row["texts_per_reply_me"] = r[1]
        row["texts_per_reply_them"] = r[2]
        row["double_texts_me"] = r[3] or 0
        row["double_texts_them"] = r[4] or 0
    for r in sessions:
        if r[0] in out:
            out[r[0]]["initiation_me"] = r[1]
    return sorted(out.values(), key=lambda x: x["bucket"])


@router.get("/persons/{person_id}/hot-days")
def person_hot_days(person_id: int, request: Request, limit: int = 8):
    db = request.app.state.db_path
    rows = run(db, f"""
        SELECT strftime(date_trunc('day', m.ts_local), '%Y-%m-%d') AS d,
               count(*) AS c,
               count(*) FILTER (WHERE m.is_from_me) AS sent,
               count(*) FILTER (WHERE NOT m.is_from_me) AS received
        {_JOIN_1TO1}
        GROUP BY 1 ORDER BY c DESC, d LIMIT ?""", [person_id, limit])
    return [{"date": r[0], "count": r[1], "sent": r[2], "received": r[3]}
            for r in rows]


@router.get("/persons/{person_id}/day-summary")
def person_day_summary(person_id: int, date: str, request: Request):
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    db = request.app.state.db_path
    name = run(db, "SELECT display_name FROM persons WHERE person_id = ?", [person_id])
    if not name:
        raise HTTPException(status_code=404, detail="unknown person")
    rows = run(db, f"""
        SELECT strftime(m.ts_local, '%H:%M') AS hm, m.is_from_me, m.text
        {_JOIN_1TO1}
        WHERE strftime(date_trunc('day', m.ts_local), '%Y-%m-%d') = ?
              AND m.text IS NOT NULL
        ORDER BY m.ts_local LIMIT 400""", [person_id, date])
    if not rows:
        raise HTTPException(status_code=404, detail="no messages on that day")
    lines = [f"{hm} {'You' if from_me else name[0][0]}: {text[:200]}"
             for hm, from_me, text in rows]
    transcript = "\n".join(lines)[:12000]
    result = summarize_day(f"{person_id}:{date}", name[0][0], date, transcript)
    return {"date": date, **result}


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
    """Multi-person series; used by the Overview relationship-arcs chart."""
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


