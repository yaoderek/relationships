import json
import os
from pathlib import Path

import duckdb
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


@router.get("/language/people-clusters")
def people_clusters(request: Request):
    rows = run(_lang_db(request), """
        SELECT cluster_id, label, person_id, name FROM person_clusters
        ORDER BY cluster_id, name""")
    out: dict[int, dict] = {}
    for cid, label, pid, name in rows:
        cluster = out.setdefault(cid, {"cluster_id": cid, "label": label,
                                       "members": []})
        cluster["members"].append({"person_id": pid, "name": name})
    return list(out.values())


@router.get("/language/people-map")
def people_map(request: Request):
    rows = run(_lang_db(request), """
        SELECT person_id, name, period, x, y, z, cluster_id, msgs
        FROM person_map ORDER BY period, name""")
    return {
        "periods": sorted({r[2] for r in rows}),
        "points": [{"person_id": r[0], "name": r[1], "period": r[2],
                    "x": r[3], "y": r[4], "z": r[5], "cluster_id": r[6],
                    "msgs": r[7]} for r in rows],
    }


@router.get("/language/semantic-experiments")
def semantic_experiments(request: Request):
    """Results of scripts/semantic.py; empty list until it has been run."""
    path = request.app.state.db_path.parent / "semantic.duckdb"
    if not path.exists():
        return []
    try:
        rows = run(path, """
            SELECT experiment, title, summary, payload
            FROM semantic_experiments ORDER BY created_at""")
    except duckdb.CatalogException:
        # scripts/semantic.py is mid-run: embeddings cached, results not yet
        return []
    out = []
    for experiment, title, summary, payload in rows:
        body = json.loads(payload)
        out.append({"experiment": experiment, "title": title,
                    "summary": summary, **body})
    return out


@router.get("/language/semantic-map")
def semantic_map(request: Request):
    """UMAP layouts + multi-resolution Leiden communities from
    scripts/semantic.py."""
    path = request.app.state.db_path.parent / "semantic.duckdb"
    if not path.exists():
        return {"communities": [], "points": [], "umap_neighbors": [],
                "umap_min_dist": [], "umap_default_neighbors": 30,
                "umap_default_min_dist": 0.05}
    try:
        points = run(path, """
            SELECT x, y, x3, y3, z3, c05, c1, c2, c4,
                   contact, start_ts, n_msgs, snippet
            FROM session_map ORDER BY session_id""")
        comms = run(path, """
            SELECT gamma, cluster_id, label, size, phrases, top_contacts,
                   years, from_me_frac, initiated_frac, median_msgs,
                   examples, parent_gamma, parent_cluster_id
            FROM semantic_communities ORDER BY gamma, size DESC""")
        try:
            nn_rows = run(path, """
                SELECT DISTINCT n_neighbors FROM session_umap_variants
                ORDER BY n_neighbors""")
            md_rows = run(path, """
                SELECT DISTINCT min_dist FROM session_umap_variants
                ORDER BY min_dist""")
            umap_neighbors = [r[0] for r in nn_rows]
            umap_min_dist = [r[0] for r in md_rows]
        except duckdb.CatalogException:
            umap_neighbors = []
            umap_min_dist = []
    except duckdb.CatalogException:
        return {"communities": [], "points": [], "umap_neighbors": [],
                "umap_min_dist": [], "umap_default_neighbors": 30,
                "umap_default_min_dist": 0.05}
    return {
        "communities": [
            {"gamma": c[0], "cluster_id": c[1], "label": c[2], "size": c[3],
             "phrases": json.loads(c[4]), "top_contacts": json.loads(c[5]),
             "years": json.loads(c[6]), "from_me_frac": c[7],
             "initiated_frac": c[8], "median_msgs": c[9],
             "examples": json.loads(c[10]), "parent_gamma": c[11],
             "parent_cluster_id": c[12]} for c in comms],
        "points": [
            {"x": p[0], "y": p[1], "x3": p[2], "y3": p[3], "z3": p[4],
             "c": [p[5], p[6], p[7], p[8]],
             "contact": p[9], "date": p[10], "n_msgs": p[11],
             "snippet": p[12]} for p in points],
        "umap_neighbors": umap_neighbors,
        "umap_min_dist": umap_min_dist,
        "umap_default_neighbors": 30,
        "umap_default_min_dist": 0.05,
    }


def _layout_key(n_neighbors: int, min_dist: float) -> str:
    return f"{n_neighbors}:{min_dist:g}"


def _load_umap_layouts(path: Path) -> dict[str, list[list[float]]]:
    rows = run(path, """
        SELECT v.n_neighbors, v.min_dist, v.x3, v.y3, v.z3
        FROM session_map m
        JOIN session_umap_variants v ON v.session_id = m.session_id
        ORDER BY v.n_neighbors, v.min_dist, m.session_id""")
    variants: dict[str, list[list[float]]] = {}
    for nn, md, x, y, z in rows:
        variants.setdefault(_layout_key(int(nn), float(md)), []).append(
            [float(x), float(y), float(z)])
    return variants


@router.get("/language/semantic-map/all-layouts")
def semantic_map_all_layouts(request: Request):
    """All precomputed UMAP 3D layouts keyed as 'n_neighbors:min_dist'."""
    path = request.app.state.db_path.parent / "semantic.duckdb"
    if not path.exists():
        return {"variants": {}}
    try:
        return {"variants": _load_umap_layouts(path)}
    except duckdb.CatalogException:
        rows = run(path, """
            SELECT x3, y3, z3 FROM session_map ORDER BY session_id""")
        layout = [[r[0], r[1], r[2]] for r in rows]
        return {"variants": {_layout_key(30, 0.05): layout}}


@router.get("/language/semantic-map/layout")
def semantic_map_layout(request: Request, n_neighbors: int = 30,
                        min_dist: float = 0.05):
    """3D coordinates for one precomputed UMAP variant (same order as
    session_map)."""
    path = request.app.state.db_path.parent / "semantic.duckdb"
    if not path.exists():
        return {"layout": []}
    try:
        rows = run(path, """
            SELECT v.x3, v.y3, v.z3
            FROM session_map m
            JOIN session_umap_variants v
              ON v.session_id = m.session_id
             AND v.n_neighbors = ?
             AND abs(v.min_dist - ?) < 1e-9
            ORDER BY m.session_id""", [n_neighbors, min_dist])
        if rows:
            return {"layout": [[r[0], r[1], r[2]] for r in rows]}
    except duckdb.CatalogException:
        pass
    if n_neighbors == 30 and abs(min_dist - 0.05) < 1e-9:
        rows = run(path, """
            SELECT x3, y3, z3 FROM session_map ORDER BY session_id""")
        return {"layout": [[r[0], r[1], r[2]] for r in rows]}
    raise HTTPException(
        status_code=404,
        detail="UMAP variant not found — rerun scripts/semantic.py --map-only")


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
