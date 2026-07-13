import random

from fastapi import APIRouter, HTTPException, Request

from ..db import run

router = APIRouter()

_TOP_N = 20
_ATTEMPTS = 20


def _top_persons(db) -> list[tuple[int, str]]:
    """Top contacts by 1:1 text-message volume, as (person_id, display_name)."""
    rows = run(db, """
        SELECT m.person_id, p.display_name, count(*) AS c
        FROM messages m
        JOIN chats c2 ON c2.chat_id = m.chat_id AND NOT c2.is_group
        JOIN persons p ON p.person_id = m.person_id
        WHERE m.text IS NOT NULL AND p.display_name NOT LIKE 'urn:%'
        GROUP BY 1, 2
        ORDER BY c DESC, m.person_id
        LIMIT ?""", [_TOP_N])
    return [(r[0], r[1]) for r in rows]


@router.get("/games/who-said-it")
def who_said_it(request: Request):
    db = request.app.state.db_path
    top = _top_persons(db)
    if len(top) < 4:
        raise HTTPException(404, "need at least 4 contacts to play")
    for _ in range(_ATTEMPTS):
        person_id, name = random.choice(top)
        sessions = run(db, """
            SELECT m.session_id
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            WHERE m.person_id = ? AND m.text IS NOT NULL
            GROUP BY 1
            HAVING count(*) >= 3
               AND count(*) FILTER (WHERE NOT m.is_from_me) >= 2""",
            [person_id])
        if not sessions:
            continue
        session_id = random.choice(sessions)[0]
        msgs = run(db, """
            SELECT trim(m.text), m.is_from_me,
                   strftime(date_trunc('day', m.ts_local), '%Y-%m-%d')
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            WHERE m.session_id = ? AND m.person_id = ? AND m.text IS NOT NULL
            ORDER BY m.ts_utc""", [session_id, person_id])
        size = min(5, len(msgs))
        windows = [msgs[i:i + size] for i in range(len(msgs) - size + 1)]
        windows = [w for w in windows if sum(not m[1] for m in w) >= 2]
        if not windows:
            continue
        window = random.choice(windows)
        others = random.sample([p for p in top if p[0] != person_id], 3)
        choices = [{"person_id": pid, "display_name": n}
                   for pid, n in [*others, (person_id, name)]]
        random.shuffle(choices)
        return {
            "messages": [{"text": t, "is_from_me": bool(f)}
                         for t, f, _ in window],
            "choices": choices,
            "answer_person_id": person_id,
            "date": window[0][2],
        }
    raise HTTPException(404, "not enough message history for this game")
