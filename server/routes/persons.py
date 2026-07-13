from fastapi import APIRouter, Request

from ..db import run

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
