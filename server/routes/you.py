from fastapi import APIRouter, Request

from ..db import run
from ..stopwords import STOPWORDS

router = APIRouter()


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
            SELECT unnest(string_split_regex(lower(text), '[^a-z'']+')) AS w
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
