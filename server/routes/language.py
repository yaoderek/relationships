import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..db import run

router = APIRouter()

_EMBED_MODEL = "text-embedding-3-small"
_DIMS = 256


def _lang_db(request: Request) -> Path:
    path = request.app.state.db_path.parent / "language.duckdb"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="language artifacts missing — run `uv run python scripts/language.py`")
    return path


@router.get("/language/topics")
def language_topics(request: Request):
    db = _lang_db(request)
    clusters = run(db, """
        SELECT cluster_id, label, msg_count, share FROM clusters
        ORDER BY msg_count DESC""")
    people = run(db, "SELECT cluster_id, name, share FROM cluster_people")
    by_cluster: dict[int, list] = {}
    for cid, name, share in people:
        by_cluster.setdefault(cid, []).append({"name": name, "share": share})
    return [{"cluster_id": c[0], "label": c[1], "msg_count": c[2],
             "share": c[3], "people": by_cluster.get(c[0], [])}
            for c in clusters]


@router.get("/language/voice")
def language_voice(request: Request):
    rows = run(_lang_db(request), """
        SELECT person_id, name, msgs, divergence, mirroring
        FROM voice_person ORDER BY msgs DESC""")
    return [{"person_id": r[0], "name": r[1], "msgs": r[2],
             "divergence": r[3], "mirroring": r[4]} for r in rows]


@router.get("/language/drift")
def language_drift(request: Request):
    rows = run(_lang_db(request),
               "SELECT month, drift, novelty FROM voice_drift ORDER BY month")
    return [{"month": r[0], "drift": r[1], "novelty": r[2]} for r in rows]


@router.get("/language/scopes")
def language_scopes(request: Request):
    rows = run(_lang_db(request), """
        SELECT DISTINCT scope, label FROM signature_phrases
        ORDER BY scope""")
    return [{"scope": r[0], "label": r[1]} for r in rows]


@router.get("/language/signature")
def language_signature(request: Request, scope: str = "you"):
    rows = run(_lang_db(request), """
        SELECT phrase, count, score FROM signature_phrases
        WHERE scope = ? ORDER BY score DESC""", [scope])
    return {"scope": scope,
            "phrases": [{"phrase": r[0], "count": r[1], "score": r[2]}
                        for r in rows]}


@router.get("/language/search")
def language_search(q: str, request: Request, limit: int = 12):
    db = _lang_db(request)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503,
                            detail="OPENAI_API_KEY not configured")
    try:
        r = httpx.post(
            "https://api.openai.com/v1/embeddings",
            json={"model": _EMBED_MODEL, "input": [q[:300]],
                  "dimensions": _DIMS},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="could not reach OpenAI")
    vec = r.json()["data"][0]["embedding"]
    rows = run(db, f"""
        SELECT text, total, mine,
               array_cosine_similarity(embedding, CAST(? AS FLOAT[{_DIMS}])) AS sim
        FROM text_embeddings
        ORDER BY sim DESC LIMIT ?""", [vec, limit])
    return [{"text": r[0], "total": r[1], "mine": r[2], "similarity": r[3]}
            for r in rows]
