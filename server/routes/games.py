import random

from fastapi import APIRouter, HTTPException, Request

from ..db import run
from ..stopwords import STOPWORDS

router = APIRouter()

_TOP_N = 20
_ATTEMPTS = 20
_MIN_WORD_USES = 3
_MIN_RATE_RATIO = 1.5
_EMBED_DIMS = 256
_NEAR_DUPLICATE_SIM = 0.95


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


def _embedding_distractors(request: Request, reply: str) -> list[str]:
    """Replies I actually sent that mean something close to the real reply.

    Uses the language.duckdb embeddings when available; returns [] when the
    artifacts are missing or the reply was never embedded, so callers can
    fall back to length matching.
    """
    lang_db = request.app.state.db_path.parent / "language.duckdb"
    if not lang_db.exists():
        return []
    lo, hi = int(len(reply) * 0.5), int(len(reply) * 2.0) + 1
    rows = run(lang_db, f"""
        WITH target AS (
            SELECT embedding FROM text_embeddings WHERE text = ? LIMIT 1
        )
        SELECT te.text,
               array_cosine_similarity(
                   te.embedding, (SELECT embedding FROM target)) AS sim
        FROM text_embeddings te
        WHERE te.mine > 0 AND lower(te.text) <> lower(?)
              AND len(te.text) BETWEEN ? AND ?
              AND EXISTS (SELECT 1 FROM target)
        ORDER BY sim DESC LIMIT 40""", [reply, reply, lo, hi])
    candidates = [t for t, sim in rows if sim is not None
                  and sim < _NEAR_DUPLICATE_SIM]
    seen: set[str] = {reply.lower()}
    unique: list[str] = []
    for t in candidates:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    if len(unique) < 3:
        return []
    # Sample from the closest ~25 so repeat rounds don't reuse one trio.
    return random.sample(unique[:25], 3)


@router.get("/games/finish-the-convo")
def finish_the_convo(request: Request):
    db = request.app.state.db_path
    top = _top_persons(db)
    if not top:
        raise HTTPException(404, "not enough contacts for this game")
    top_names = dict(top)
    candidates = run(db, """
        WITH ordered AS (
            SELECT m.msg_id, m.chat_id, m.person_id, m.is_from_me,
                   trim(m.text) AS text, m.session_id,
                   row_number() OVER w AS rn,
                   lag(m.is_from_me) OVER w AS prev_from_me,
                   lag(m.session_id) OVER w AS prev_session,
                   row_number() OVER (PARTITION BY m.chat_id, m.session_id
                                      ORDER BY m.ts_utc) AS srn
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            WHERE m.text IS NOT NULL
            WINDOW w AS (PARTITION BY m.chat_id ORDER BY m.ts_utc)
        )
        SELECT msg_id, chat_id, person_id, rn, text FROM ordered
        WHERE is_from_me AND len(text) >= 8
              AND prev_from_me = FALSE AND prev_session = session_id
              AND srn >= 5""")
    candidates = [c for c in candidates if c[2] in top_names]
    if not candidates:
        raise HTTPException(404, "not enough message history for this game")
    for _ in range(_ATTEMPTS):
        msg_id, chat_id, person_id, rn, reply = random.choice(candidates)
        rows = run(db, """
            WITH ordered AS (
                SELECT trim(m.text) AS text, m.is_from_me,
                       strftime(date_trunc('day', m.ts_local), '%Y-%m-%d') AS d,
                       row_number() OVER (PARTITION BY m.chat_id
                                          ORDER BY m.ts_utc) AS rn
                FROM messages m
                JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
                WHERE m.text IS NOT NULL AND m.chat_id = ?
            )
            SELECT text, is_from_me, d, rn FROM ordered
            WHERE rn BETWEEN ? AND ? ORDER BY rn""",
            [chat_id, rn - 4, rn + 3])
        context = [r for r in rows if r[3] < rn]
        aftermath = [r for r in rows if r[3] > rn]
        distractors = _embedding_distractors(request, reply)
        if not distractors:
            lo, hi = int(len(reply) * 0.6), int(len(reply) * 1.4) + 1
            pool = run(db, """
                SELECT DISTINCT trim(text) FROM messages
                WHERE is_from_me AND text IS NOT NULL AND chat_id <> ?
                      AND len(trim(text)) BETWEEN ? AND ?
                ORDER BY random() LIMIT 12""", [chat_id, lo, hi])
            seen = {reply.lower()}
            distractors = []
            for (t,) in pool:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    distractors.append(t)
                if len(distractors) == 3:
                    break
        if len(distractors) < 3:
            continue
        options = [reply, *distractors]
        random.shuffle(options)
        return {
            "context": [{"text": t, "is_from_me": bool(f)}
                        for t, f, _, _ in context],
            "options": options,
            "answer_index": options.index(reply),
            "person_name": top_names[person_id],
            "date": context[-1][2],
            "aftermath": [{"text": t, "is_from_me": bool(f)}
                          for t, f, _, _ in aftermath],
        }
    raise HTTPException(404, "not enough message history for this game")


@router.get("/games/which-group-chat")
def which_group_chat(request: Request):
    db = request.app.state.db_path
    groups = run(db, """
        SELECT c.chat_id, c.name, count(*) AS cnt
        FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id AND c.is_group
        WHERE m.text IS NOT NULL
              AND c.name IS NOT NULL AND len(trim(c.name)) > 0
        GROUP BY 1, 2
        ORDER BY cnt DESC, c.chat_id
        LIMIT ?""", [_TOP_N])
    if len(groups) < 4:
        raise HTTPException(404, "need at least 4 named group chats to play")
    for _ in range(_ATTEMPTS):
        chat_id, name, _cnt = random.choice(groups)
        sessions = run(db, """
            SELECT session_id FROM messages
            WHERE chat_id = ? AND text IS NOT NULL
            GROUP BY 1 HAVING count(*) >= 4""", [chat_id])
        if not sessions:
            continue
        session_id = random.choice(sessions)[0]
        msgs = run(db, """
            SELECT trim(text), is_from_me,
                   strftime(date_trunc('day', ts_local), '%Y-%m-%d')
            FROM messages
            WHERE chat_id = ? AND session_id = ? AND text IS NOT NULL
            ORDER BY ts_utc""", [chat_id, session_id])
        size = min(6, len(msgs))
        start = random.randrange(len(msgs) - size + 1)
        window = msgs[start:start + size]
        others = random.sample([g for g in groups if g[0] != chat_id], 3)
        choices = [{"chat_id": cid, "name": n}
                   for cid, n, _ in [*others, (chat_id, name, 0)]]
        random.shuffle(choices)
        return {
            "messages": [{"text": t, "is_from_me": bool(f)}
                         for t, f, _ in window],
            "choices": choices,
            "answer_chat_id": chat_id,
            "date": window[0][2],
        }
    raise HTTPException(404, "not enough group chat history for this game")


@router.get("/games/who-says-it-more")
def who_says_it_more(request: Request):
    db = request.app.state.db_path
    top = _top_persons(db)
    if len(top) < 2:
        raise HTTPException(404, "need at least 2 contacts to play")
    top_names = dict(top)
    person_ph = ", ".join("?" for _ in top)
    stop_ph = ", ".join("?" for _ in STOPWORDS)
    person_ids = [pid for pid, _ in top]
    rows = run(db, f"""
        WITH totals AS (
            SELECT m.person_id, count(*) AS total
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            WHERE NOT m.is_from_me AND m.text IS NOT NULL
                  AND m.person_id IN ({person_ph})
            GROUP BY 1
        ),
        words AS (
            SELECT m.person_id,
                   unnest(string_split_regex(
                       replace(lower(m.text), '’', ''''), '[^a-z'']+')) AS w
            FROM messages m
            JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
            WHERE NOT m.is_from_me AND m.text IS NOT NULL
                  AND m.person_id IN ({person_ph})
        )
        SELECT w.person_id, w.w, count(*) AS c, t.total
        FROM words w JOIN totals t ON t.person_id = w.person_id
        WHERE len(w.w) >= 3 AND w.w NOT IN ({stop_ph})
        GROUP BY 1, 2, 4 HAVING count(*) >= ?""",
        [*person_ids, *person_ids, *STOPWORDS, _MIN_WORD_USES])
    by_word: dict[str, list[tuple[int, int, float]]] = {}
    for person_id, word, count, total in rows:
        rate = count / total * 1000
        by_word.setdefault(word, []).append((person_id, count, rate))
    playable = {w: users for w, users in by_word.items() if len(users) >= 2}
    if not playable:
        raise HTTPException(404, "not enough shared vocabulary for this game")
    for _ in range(_ATTEMPTS):
        word = random.choice(sorted(playable))
        a, b = random.sample(playable[word], 2)
        low, high = sorted((a, b), key=lambda u: u[2])
        if low[2] <= 0 or high[2] / low[2] < _MIN_RATE_RATIO:
            continue
        choices = [{"person_id": pid, "display_name": top_names[pid],
                    "count": count, "per_1k": round(rate, 1)}
                   for pid, count, rate in (a, b)]
        random.shuffle(choices)
        return {
            "word": word,
            "choices": choices,
            "answer_person_id": high[0],
        }
    raise HTTPException(404, "no word with meaningfully different usage found")
