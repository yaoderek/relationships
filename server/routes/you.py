import re

from fastapi import APIRouter, Request

from ..db import run
from ..stopwords import STOPWORDS

router = APIRouter()


@router.get("/you/word-context")
def you_word_context(word: str, request: Request):
    pattern = r"\b" + re.escape(word.lower()) + r"\b"
    rows = run(request.app.state.db_path, """
        SELECT trim(text) AS s, count(*) AS c
        FROM messages
        WHERE is_from_me AND text IS NOT NULL
              AND regexp_matches(replace(lower(text), '’', ''''), ?)
        GROUP BY 1 ORDER BY c DESC, s LIMIT 5""", [pattern])
    return [{"text": r[0], "count": r[1]} for r in rows]


@router.get("/you/vernacular-timeline")
def you_vernacular_timeline(request: Request):
    placeholders = ", ".join("?" for _ in STOPWORDS)
    rows = run(request.app.state.db_path, f"""
        WITH words AS (
            SELECT strftime(date_trunc('year', ts_local), '%Y') AS y,
                   unnest(string_split_regex(
                       replace(lower(text), '’', ''''), '[^a-z'']+')) AS w
            FROM messages WHERE is_from_me AND text IS NOT NULL
        ),
        counts AS (
            SELECT y, w, count(*) AS c FROM words
            WHERE len(w) >= 3 AND w NOT IN ({placeholders})
            GROUP BY 1, 2
        ),
        ranked AS (
            SELECT *, row_number() OVER (PARTITION BY y ORDER BY c DESC, w) AS rn
            FROM counts
        )
        SELECT y, w, c FROM ranked WHERE rn <= 8 ORDER BY y, rn""",
        [*STOPWORDS])
    out: dict[str, list] = {}
    for y, w, c in rows:
        out.setdefault(y, []).append({"word": w, "count": c})
    return [{"bucket": y, "words": ws} for y, ws in sorted(out.items())]


@router.get("/you/catchphrases-timeline")
def you_catchphrases_timeline(request: Request):
    rows = run(request.app.state.db_path, """
        WITH s AS (
            SELECT strftime(date_trunc('year', ts_local), '%Y') AS y,
                   trim(text) AS t
            FROM messages
            WHERE is_from_me AND text IS NOT NULL AND len(trim(text)) >= 8
        ),
        counts AS (
            SELECT y, t, count(*) AS c FROM s
            GROUP BY 1, 2 HAVING count(*) >= 2
        ),
        ranked AS (
            SELECT *, row_number() OVER (PARTITION BY y ORDER BY c DESC, t) AS rn
            FROM counts
        )
        SELECT y, t, c FROM ranked WHERE rn <= 5 ORDER BY y, rn""")
    out: dict[str, list] = {}
    for y, t, c in rows:
        out.setdefault(y, []).append({"text": t, "count": c})
    return [{"bucket": y, "sentences": s} for y, s in sorted(out.items())]


@router.get("/you/hot-days")
def you_hot_days(request: Request, limit: int = 10):
    rows = run(request.app.state.db_path, """
        WITH d AS (
            SELECT strftime(date_trunc('day', ts_local), '%Y-%m-%d') AS day,
                   is_from_me, person_id
            FROM messages
        ),
        days AS (
            SELECT day, count(*) AS c,
                   count(*) FILTER (WHERE is_from_me) AS sent
            FROM d GROUP BY 1 ORDER BY c DESC, day LIMIT ?
        ),
        tops AS (
            SELECT d.day, p.display_name,
                   row_number() OVER (PARTITION BY d.day
                                      ORDER BY count(*) DESC, p.display_name) AS rn
            FROM d JOIN persons p ON p.person_id = d.person_id
            WHERE p.display_name NOT LIKE 'urn:%'
            GROUP BY d.day, p.display_name
        )
        SELECT days.day, days.c, days.sent, t.display_name
        FROM days LEFT JOIN tops t ON t.day = days.day AND t.rn = 1
        ORDER BY days.c DESC, days.day""", [limit])
    return [{"date": r[0], "count": r[1], "sent": r[2], "top_contact": r[3]}
            for r in rows]


@router.get("/you")
def you_stats(request: Request):
    db = request.app.state.db_path

    totals = run(db, """
        SELECT count(*), avg(char_len), sum(emoji_count),
               count(*) FILTER (WHERE c.is_group),
               count(*) FILTER (WHERE NOT c.is_group)
        FROM messages m JOIN chats c ON c.chat_id = m.chat_id
        WHERE m.is_from_me""")[0]

    placeholders = ", ".join("?" for _ in STOPWORDS)
    top_words = run(db, f"""
        SELECT w AS word, count(*) AS c FROM (
            SELECT unnest(string_split_regex(
                replace(lower(text), '’', ''''), '[^a-z'']+')) AS w
            FROM messages WHERE is_from_me AND text IS NOT NULL)
        WHERE len(w) >= 3 AND w NOT IN ({placeholders})
        GROUP BY 1 ORDER BY c DESC, w LIMIT 15""", [*STOPWORDS])

    top_sentences = run(db, """
        SELECT trim(text) AS s, count(*) AS c
        FROM messages
        WHERE is_from_me AND text IS NOT NULL AND len(trim(text)) >= 8
        GROUP BY 1 HAVING count(*) >= 3
        ORDER BY c DESC, s LIMIT 10""")

    top_emojis = run(db, """
        SELECT e.emoji, count(*) AS c FROM emoji_uses e
        JOIN messages m ON m.msg_id = e.msg_id
        WHERE m.is_from_me GROUP BY 1 ORDER BY c DESC LIMIT 10""")

    reactions_given = run(db, """
        SELECT kind, count(*) FROM tapbacks WHERE is_from_me
        GROUP BY 1 ORDER BY 2 DESC""")

    heatmap = run(db, """
        SELECT dayofweek(ts_local) AS weekday, hour(ts_local) AS hour, count(*)
        FROM messages WHERE is_from_me GROUP BY 1, 2 ORDER BY 1, 2""")

    busiest = run(db, """
        SELECT strftime(date_trunc('day', ts_local), '%Y-%m-%d') AS d, count(*) AS c
        FROM messages WHERE is_from_me
        GROUP BY 1 ORDER BY c DESC, d LIMIT 1""")

    blocks = run(db, """
        WITH flagged AS (
            SELECT is_from_me, chat_id, ts_utc,
                   CASE WHEN lag(is_from_me) OVER w = is_from_me
                             AND lag(session_id) OVER w = session_id
                        THEN 0 ELSE 1 END AS new_block,
                   CASE WHEN lag(is_from_me) OVER w = is_from_me
                             AND date_diff('second', lag(ts_utc) OVER w, ts_utc) >= 600
                        THEN 1 ELSE 0 END AS double_text
            FROM messages
            WINDOW w AS (PARTITION BY chat_id ORDER BY ts_utc)
        ),
        block_sizes AS (
            SELECT any_value(is_from_me) AS is_from_me, count(*) AS n
            FROM (SELECT *, sum(new_block) OVER (PARTITION BY chat_id ORDER BY ts_utc)
                         AS block_id
                  FROM flagged)
            GROUP BY chat_id, block_id
        )
        SELECT (SELECT avg(n) FROM block_sizes WHERE is_from_me),
               (SELECT count(*) FROM flagged WHERE double_text = 1 AND is_from_me)
        """)[0]

    return {
        "sent_total": totals[0], "avg_chars": totals[1],
        "emoji_total": totals[2] or 0,
        "sent_in_groups": totals[3], "sent_in_dms": totals[4],
        "top_words": [{"word": r[0], "count": r[1]} for r in top_words],
        "top_sentences": [{"text": r[0], "count": r[1]} for r in top_sentences],
        "top_emojis": [{"emoji": r[0], "count": r[1]} for r in top_emojis],
        "reactions_given": [{"kind": r[0], "count": r[1]} for r in reactions_given],
        "heatmap": [{"weekday": r[0], "hour": r[1], "count": r[2]} for r in heatmap],
        "busiest_day": ({"date": busiest[0][0], "count": busiest[0][1]}
                        if busiest else None),
        "avg_texts_per_reply": blocks[0],
        "double_texts": blocks[1],
    }
