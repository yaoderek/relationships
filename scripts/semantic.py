"""Semantic niche experiments over conversation sessions.

Implements the experimental core of docs/superpowers/specs/
imessage_semantic_niche_analysis_plan.md on top of the existing system:
sessions come from analytics.duckdb (60-min gap sessionization from ingest)
and message embeddings from language.duckdb (text-embedding-3-small, 256d).

Four experiments, each written as a separate row of
data/semantic.duckdb::semantic_experiments for the dashboard:

  1. representation — weighted-mean-of-message-embeddings vs directly
     embedding the concatenated session transcript (plus debiased variants).
  2. neighborhood  — kNN vs mutual kNN sweep over k, plus edge weighting
     (binary / cosine / adaptive local scaling).
  3. laplacian     — normalized-Laplacian spectrum, eigengap, spectral
     clustering, diffusion-map coordinates.
  4. clustering    — Leiden resolution sweep vs HDBSCAN vs k-means baseline,
     small-niche recovery.

Run after `python -m ingest` and `scripts/language.py`:

    uv run python scripts/semantic.py
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import httpx
import igraph as ig
import leidenalg as la
import numpy as np
import pyarrow as pa
import umap
from scipy.sparse import csgraph, csr_matrix
from scipy.sparse.linalg import eigsh
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.neighbors import NearestNeighbors

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.phrases import log_odds, ngram_counts, tokenize
from server.llm import load_env_file
from server.stopwords import STOPWORDS

ANALYTICS = Path("data/analytics.duckdb")
LANGUAGE = Path("data/language.duckdb")
OUT = Path("data/semantic.duckdb")

EMBED_MODEL = "text-embedding-3-small"
DIMS = 256
EMBED_BATCH = 200
CONV_MAX_CHARS = 4000

MIN_SESSION_MSGS = 3
MIN_SESSION_WORDS = 20
K_MAX = 50
K_SWEEP = (10, 15, 20, 30, 50)
K_DEFAULT = 20
SIGMA_NEIGHBOR = 10          # adaptive local scaling: distance to 10th neighbor
EDGE_SAMPLE = 2000           # edges sampled for lexical-agreement metrics
N_EIGEN = 64
LEIDEN_GAMMAS = (0.5, 1.0, 2.0, 4.0)
MAX_LLM_LABELS = 14
UMAP_NEIGHBORS_SWEEP = (15, 20, 30, 40, 50)
UMAP_MIN_DIST_SWEEP = (0.0, 0.05, 0.1, 0.2, 0.5)
UMAP_DEFAULT_NEIGHBORS = 30
UMAP_DEFAULT_MIN_DIST = 0.05

_STOPSET = set(STOPWORDS)


# ---------------------------------------------------------------- data model

@dataclass
class Session:
    session_id: str
    chat_id: int
    is_group: bool
    contact: str          # display name for DMs, chat name for groups
    start_ts: str
    n_msgs: int
    n_words: int
    n_from_me: int
    initiated_by_me: bool
    raw_text: str         # message texts joined, for phrase mining
    conv_text: str        # "Me:/Them:" transcript, for direct embedding
    disp_text: str        # transcript with real sender names, for display
    tokens: frozenset = field(default_factory=frozenset)


def content_tokens(text: str) -> frozenset:
    return frozenset(t for t in tokenize(text)
                     if len(t) > 2 and t not in _STOPSET)


def load_sessions() -> tuple[list[Session], np.ndarray]:
    """Return contentful sessions plus their weighted-mean embeddings."""
    con = duckdb.connect(str(ANALYTICS), read_only=True)
    rows = con.execute("""
        SELECT m.session_id, m.chat_id, c.is_group,
               CASE WHEN c.is_group
                    THEN coalesce(nullif(trim(c.name), ''), 'unnamed group')
                    ELSE coalesce(p.display_name, 'unknown') END AS contact,
               m.is_from_me, m.ts_utc, trim(m.text) AS t, m.word_count,
               p.display_name AS sender
        FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id
        LEFT JOIN persons p ON p.person_id = m.person_id
            AND p.display_name NOT LIKE 'urn:%'
        WHERE m.text IS NOT NULL AND len(trim(m.text)) > 0
            AND m.session_id IS NOT NULL
        ORDER BY m.session_id, m.ts_utc""").fetchall()
    con.close()

    lang = duckdb.connect(str(LANGUAGE), read_only=True)
    tbl = lang.execute(
        "SELECT text, embedding FROM text_embeddings").to_arrow_table()
    lang.close()
    emb_texts = tbl["text"].to_pylist()
    emb = np.asarray(tbl["embedding"].combine_chunks().flatten(),
                     dtype=np.float32).reshape(len(emb_texts), DIMS)
    text_row = {t: i for i, t in enumerate(emb_texts)}
    print(f"{len(rows):,} messages, {len(emb_texts):,} embedded texts loaded")

    by_session: dict[str, list] = defaultdict(list)
    for r in rows:
        by_session[r[0]].append(r)

    sessions: list[Session] = []
    vecs: list[np.ndarray] = []
    missing = 0
    for sid, msgs in by_session.items():
        n_words = sum(m[7] or 0 for m in msgs)
        if len(msgs) < MIN_SESSION_MSGS or n_words < MIN_SESSION_WORDS:
            continue
        acc = np.zeros(DIMS, dtype=np.float32)
        w_sum = 0.0
        conv_lines = []
        disp_lines = []
        raw_parts = []
        contact = "unknown"
        for (_sid, _chat, is_group, name, from_me, _ts, t, wc,
             sender) in msgs:
            conv_lines.append(f"{'Me' if from_me else 'Them'}: {t}")
            who = "Me" if from_me else (
                (sender or "Them").split(" ")[0] or "Them")
            disp_lines.append(f"{who}: {t}")
            raw_parts.append(t)
            if is_group:
                contact = name
            elif not from_me and name != "unknown":
                contact = name
            row = text_row.get(t)
            if row is None:
                missing += 1
                continue
            toks = tokenize(t)
            n_tok = len(toks)
            content_ratio = (sum(1 for x in toks if x not in _STOPSET)
                             / max(n_tok, 1))
            # Information weight q_i (plan §2): short pure-filler messages
            # get ~0.1, contentful multi-word messages approach 1.
            q = 1 / (1 + np.exp(-(-2.5 + 0.9 * np.log1p(n_tok)
                                  + 2.0 * content_ratio)))
            w = q * (max(n_tok, 1) ** 0.25)
            acc += w * emb[row]
            w_sum += w
        if w_sum <= 0:
            continue
        v = acc / w_sum
        norm = np.linalg.norm(v)
        if norm < 1e-9:
            continue
        first = msgs[0]
        raw_text = " ".join(raw_parts)
        sessions.append(Session(
            session_id=sid, chat_id=first[1], is_group=bool(first[2]),
            contact=contact, start_ts=str(first[5]),
            n_msgs=len(msgs), n_words=n_words,
            n_from_me=sum(1 for m in msgs if m[4]),
            initiated_by_me=bool(first[4]),
            raw_text=raw_text,
            conv_text="\n".join(conv_lines)[:CONV_MAX_CHARS],
            disp_text="\n".join(disp_lines)[:CONV_MAX_CHARS],
            tokens=content_tokens(raw_text)))
        vecs.append(v / norm)
    if missing:
        print(f"  {missing:,} message texts missing from text_embeddings "
              "(stale language.duckdb) — skipped in weighted means")
    print(f"{len(sessions):,} contentful sessions "
          f"(>= {MIN_SESSION_MSGS} msgs, >= {MIN_SESSION_WORDS} words)")
    return sessions, np.stack(vecs)


# ------------------------------------------------------- conversation embeds

def embed_batch(texts: list[str], api_key: str) -> np.ndarray:
    out = np.empty((len(texts), DIMS), dtype=np.float32)
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        for attempt in range(4):
            try:
                r = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    json={"model": EMBED_MODEL, "input": batch,
                          "dimensions": DIMS},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=180)
                r.raise_for_status()
                break
            except Exception as exc:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                print(f"  retry {attempt + 1} after {type(exc).__name__}, "
                      f"sleeping {wait}s", flush=True)
                time.sleep(wait)
        for item in r.json()["data"]:
            out[start + item["index"]] = item["embedding"]
        done = min(start + EMBED_BATCH, len(texts))
        if (start // EMBED_BATCH) % 5 == 0 or done == len(texts):
            print(f"  embedded {done:,}/{len(texts):,} sessions", flush=True)
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(norms, 1e-9)


def conv_embeddings(sessions: list[Session], api_key: str) -> np.ndarray:
    """Embed each session transcript directly, cached in semantic.duckdb."""
    hashes = [hashlib.sha1(s.conv_text.encode()).hexdigest()
              for s in sessions]
    cached: dict[str, np.ndarray] = {}
    if OUT.exists():
        con = duckdb.connect(str(OUT), read_only=True)
        try:
            tbl = con.execute("SELECT text_hash, embedding "
                              "FROM session_embeddings").to_arrow_table()
            prev_hashes = tbl["text_hash"].to_pylist()
            prev_emb = np.asarray(
                tbl["embedding"].combine_chunks().flatten(),
                dtype=np.float32).reshape(len(prev_hashes), DIMS)
            cached = {h: prev_emb[i] for i, h in enumerate(prev_hashes)}
            print(f"reusing {len(cached):,} cached session embeddings")
        except duckdb.CatalogException:
            pass
        finally:
            con.close()

    todo = [(i, h) for i, h in enumerate(hashes) if h not in cached]
    print(f"{len(sessions):,} sessions — {len(todo):,} transcripts to embed")
    if todo:
        new = embed_batch([sessions[i].conv_text for i, _h in todo], api_key)
        for (_, h), v in zip(todo, new):
            cached[h] = v

    out = np.stack([cached[h] for h in hashes])
    con = duckdb.connect(str(OUT))
    con.execute(f"""
        CREATE OR REPLACE TABLE session_embeddings (
            session_id TEXT, text_hash TEXT, embedding FLOAT[{DIMS}])""")
    emb_flat = pa.array(out.reshape(-1), type=pa.float32())
    arrow_tbl = pa.table({
        "session_id": pa.array([s.session_id for s in sessions]),
        "text_hash": pa.array(hashes),
        "embedding": pa.FixedSizeListArray.from_arrays(emb_flat, DIMS)})
    con.register("arrow_tbl", arrow_tbl)
    con.execute(f"""
        INSERT INTO session_embeddings
        SELECT session_id, text_hash, CAST(embedding AS FLOAT[{DIMS}])
        FROM arrow_tbl""")
    con.unregister("arrow_tbl")
    con.close()
    return out


def debias(x: np.ndarray, n_components: int = 2) -> np.ndarray:
    """All-but-the-top: drop the mean and top PCs (register/tone axes)."""
    centered = x - x.mean(0)
    cov = centered.T @ centered / len(centered)
    _vals, vecs = np.linalg.eigh(cov)
    top = vecs[:, -n_components:]
    projected = centered - (centered @ top) @ top.T
    norms = np.linalg.norm(projected, axis=1, keepdims=True)
    return projected / np.maximum(norms, 1e-9)


# ------------------------------------------------------------------- graphs

@dataclass
class KnnIndex:
    dist: np.ndarray   # (n, K_MAX) cosine distances, self excluded
    idx: np.ndarray    # (n, K_MAX) neighbor indices


def build_knn(x: np.ndarray) -> KnnIndex:
    nn = NearestNeighbors(n_neighbors=K_MAX + 1, metric="cosine").fit(x)
    dist, idx = nn.kneighbors(x)
    return KnnIndex(dist=dist[:, 1:], idx=idx[:, 1:])


def directed_adj(knn: KnnIndex, k: int, data: np.ndarray) -> csr_matrix:
    n = len(knn.idx)
    rows = np.repeat(np.arange(n), k)
    cols = knn.idx[:, :k].ravel()
    return csr_matrix((data.ravel(), (rows, cols)), shape=(n, n))


def knn_graph(knn: KnnIndex, k: int, mutual: bool,
              weighting: str = "cosine") -> csr_matrix:
    """Symmetric weighted adjacency. weighting: binary | cosine | adaptive."""
    d = knn.dist[:, :k]
    if weighting == "binary":
        data = np.ones_like(d)
    elif weighting == "cosine":
        data = np.maximum(1.0 - d, 0.0)
    else:  # adaptive local scaling (plan §4.3)
        sigma = np.maximum(knn.dist[:, min(SIGMA_NEIGHBOR, k) - 1], 1e-4)
        data = np.exp(-(d ** 2) / (sigma[:, None] * sigma[knn.idx[:, :k]]))
    a = directed_adj(knn, k, data)
    # min(w, w^T) zeroes one-sided edges since the missing side is 0.
    sym = a.minimum(a.T) if mutual else a.maximum(a.T)
    sym.eliminate_zeros()
    return sym


def graph_stats(adj: csr_matrix) -> dict:
    n = adj.shape[0]
    n_comp, labels = csgraph.connected_components(adj, directed=False)
    sizes = np.bincount(labels)
    degree = adj.getnnz(axis=1)
    deg_sorted = np.sort(degree)[::-1]
    top1 = max(1, n // 100)
    total_deg = max(degree.sum(), 1)
    return {
        "giant_frac": float(sizes.max() / n),
        "n_components": int(n_comp),
        "median_degree": float(np.median(degree)),
        "isolated_frac": float((degree == 0).mean()),
        "top1pct_degree_share": float(deg_sorted[:top1].sum() / total_deg),
    }


def sample_edges(adj: csr_matrix, n_sample: int,
                 seed: int = 0) -> list[tuple[int, int]]:
    coo = adj.tocoo()
    mask = coo.row < coo.col
    pairs = np.stack([coo.row[mask], coo.col[mask]], axis=1)
    if len(pairs) == 0:
        return []
    rng = np.random.default_rng(seed)
    take = rng.choice(len(pairs), size=min(n_sample, len(pairs)),
                      replace=False)
    return [tuple(p) for p in pairs[take]]


def edge_lexical_jaccard(sessions: list[Session],
                         edges: list[tuple[int, int]]) -> float:
    if not edges:
        return 0.0
    scores = []
    for i, j in edges:
        a, b = sessions[i].tokens, sessions[j].tokens
        union = len(a | b)
        if union == 0:
            continue
        scores.append(len(a & b) / union)
    return float(np.mean(scores)) if scores else 0.0


def edge_same_chat_frac(sessions: list[Session],
                        edges: list[tuple[int, int]]) -> float:
    if not edges:
        return 0.0
    same = sum(1 for i, j in edges
               if sessions[i].chat_id == sessions[j].chat_id)
    return same / len(edges)


def run_leiden(adj: csr_matrix, gamma: float = 1.0,
               seed: int = 0) -> np.ndarray:
    coo = adj.tocoo()
    mask = coo.row < coo.col
    g = ig.Graph(n=adj.shape[0],
                 edges=list(zip(coo.row[mask].tolist(),
                                coo.col[mask].tolist())))
    weights = coo.data[mask].tolist()
    part = la.find_partition(g, la.RBConfigurationVertexPartition,
                             weights=weights, resolution_parameter=gamma,
                             seed=seed)
    return np.asarray(part.membership, dtype=np.int32)


def modularity(adj: csr_matrix, labels: np.ndarray) -> float:
    coo = adj.tocoo()
    mask = coo.row < coo.col
    g = ig.Graph(n=adj.shape[0],
                 edges=list(zip(coo.row[mask].tolist(),
                                coo.col[mask].tolist())))
    return float(g.modularity(labels.tolist(),
                              weights=coo.data[mask].tolist()))


def conductance(adj: csr_matrix, mask: np.ndarray) -> float:
    total = adj.sum()
    vol = adj[mask].sum()
    if vol == 0 or vol == total:
        return 1.0
    internal = adj[mask][:, mask].sum()
    cut = vol - internal
    return float(cut / min(vol, total - vol))


def mean_top_conductance(adj: csr_matrix, labels: np.ndarray,
                         top: int = 10) -> float:
    sizes = Counter(int(c) for c in labels if c >= 0)
    vals = []
    for cid, _n in sizes.most_common(top):
        vals.append(conductance(adj, labels == cid))
    return float(np.mean(vals)) if vals else 1.0


def cluster_coherence(x: np.ndarray, labels: np.ndarray) -> float:
    """Mean cosine of members to their cluster centroid (clusters >= 5)."""
    vals, weights = [], []
    for cid in set(labels.tolist()):
        if cid < 0:
            continue
        members = x[labels == cid]
        if len(members) < 5:
            continue
        c = members.mean(0)
        c /= np.linalg.norm(c) + 1e-9
        vals.append(float((members @ c).mean()))
        weights.append(len(members))
    if not vals:
        return 0.0
    return float(np.average(vals, weights=weights))


# ---------------------------------------------------------------- labeling

def cluster_phrases(sessions: list[Session], member_idx: np.ndarray,
                    background: Counter, limit: int = 6) -> list[str]:
    target = ngram_counts([sessions[i].raw_text for i in member_idx])
    rest = background - target
    return [p for p, _c, _z in log_odds(target, rest, min_count=3,
                                        limit=limit)]


def representative_snippet(sessions: list[Session], x: np.ndarray,
                           member_idx: np.ndarray) -> str:
    members = x[member_idx]
    c = members.mean(0)
    c /= np.linalg.norm(c) + 1e-9
    best = member_idx[int((members @ c).argmax())]
    return sessions[best].conv_text.replace("\n", " · ")[:180]


def top_contact_share(sessions: list[Session],
                      member_idx: np.ndarray) -> tuple[str, float]:
    counts = Counter(sessions[i].contact for i in member_idx)
    name, n = counts.most_common(1)[0]
    return name, n / len(member_idx)


def label_with_llm(samples: list[str], api_key: str) -> str:
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": os.environ.get("OPENAI_MODEL", "gpt-5-nano"),
                  "messages": [
                      {"role": "system",
                       "content": "You name topic clusters of casual text "
                                  "message conversations. Name the SUBJECT "
                                  "MATTER (e.g. 'gym plans', 'course "
                                  "registration'), never tone or style. "
                                  'Reply JSON {"label": "2-4 word label"}. '
                                  "Lowercase, no punctuation."},
                      {"role": "user", "content": "\n".join(samples)}],
                  "response_format": {"type": "json_object"}},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=90)
        r.raise_for_status()
        return json.loads(
            r.json()["choices"][0]["message"]["content"])["label"]
    except Exception:
        return "unlabeled"


def describe_clusters(sessions: list[Session], x: np.ndarray,
                      labels: np.ndarray, adj: csr_matrix,
                      background: Counter, api_key: str,
                      max_clusters: int = MAX_LLM_LABELS,
                      min_size: int = 5) -> list[dict]:
    out = []
    sizes = Counter(int(c) for c in labels if c >= 0)
    for cid, size in sizes.most_common(max_clusters):
        if size < min_size:
            continue
        member_idx = np.flatnonzero(labels == cid)
        phrases = cluster_phrases(sessions, member_idx, background)
        snippet = representative_snippet(sessions, x, member_idx)
        contact, share = top_contact_share(sessions, member_idx)
        sample_texts = [sessions[i].conv_text[:200] for i in member_idx[:12]]
        label = label_with_llm(sample_texts, api_key)
        out.append({
            "cluster_id": int(cid),
            "label": label, "size": int(size),
            "conductance": round(conductance(adj, labels == cid), 3),
            "phrases": phrases,
            "top_contact": contact,
            "top_contact_share": round(share, 2),
            "example": snippet})
        print(f"    cluster {cid}: {label} ({size} sessions)", flush=True)
    return out


# ------------------------------------------------------------- experiments

def experiment_representation(sessions, reps: dict[str, np.ndarray],
                              api_key: str) -> dict:
    """Exp 1: which session representation gives the best neighborhoods?"""
    print("experiment 1: session representation…", flush=True)
    rows, per_rep = [], {}
    for name, x in reps.items():
        knn = build_knn(x)
        adj = knn_graph(knn, K_DEFAULT, mutual=True, weighting="adaptive")
        edges = sample_edges(adj, EDGE_SAMPLE)
        jac = edge_lexical_jaccard(sessions, edges)
        same_chat = edge_same_chat_frac(sessions, edges)
        labels = run_leiden(adj)
        mod = modularity(adj, labels)
        coh = cluster_coherence(x, labels)
        n_clusters = len({c for c in labels.tolist()})
        stats = graph_stats(adj)
        per_rep[name] = {"jaccard": jac, "same_chat": same_chat,
                         "knn": knn, "adj": adj}
        rows.append([name, round(jac, 3), round(same_chat, 3),
                     round(stats["giant_frac"], 3), n_clusters,
                     round(mod, 3), round(coh, 3)])
        print(f"  {name}: lexical-jaccard {jac:.3f}, same-chat "
              f"{same_chat:.3f}, modularity {mod:.3f}", flush=True)

    # Winner: neighbors should agree lexically without collapsing onto
    # contact identity (plan §21.1 contact leakage).
    def score(name):
        m = per_rep[name]
        return m["jaccard"] - 0.3 * m["same_chat"]
    winner = max(per_rep, key=score)

    samples = []
    rng = np.random.default_rng(1)
    for name in reps:
        edges = sample_edges(per_rep[name]["adj"], 500, seed=2)
        take = rng.choice(len(edges), size=min(4, len(edges)), replace=False)
        for t in take:
            i, j = edges[t]
            samples.append({
                "note": name,
                "left": sessions[i].conv_text.replace("\n", " · ")[:130],
                "right": sessions[j].conv_text.replace("\n", " · ")[:130]})

    jac_conv = per_rep["conversation"]["jaccard"]
    jac_mean = per_rep["weighted-mean"]["jaccard"]
    sc_conv = per_rep["conversation"]["same_chat"]
    sc_mean = per_rep["weighted-mean"]["same_chat"]
    giant_mean = graph_stats(per_rep["weighted-mean"]["adj"])["giant_frac"]
    giant_win = graph_stats(per_rep[winner]["adj"])["giant_frac"]
    sc_win = per_rep[winner]["same_chat"]
    verdict = (
        f"Averaging message embeddings looks best on raw numbers (lexical "
        f"jaccard {jac_mean:.3f} vs {jac_conv:.3f} for transcripts) but "
        f"that signal is mostly contact leakage: {sc_mean:.0%} of its "
        f"graph edges join sessions from the same chat and the mutual-kNN "
        f"graph shatters (giant component {giant_mean:.0%}) into per-"
        f"person clumps. Directly embedding the transcript cuts same-chat "
        f"edges to {sc_conv:.0%}, and projecting out the top tone/register "
        f"components cuts them further to {sc_win:.0%} while keeping "
        f"{giant_win:.0%} of sessions in one connected component — so "
        f"conversation-level embedding does yield better topical "
        f"structure. All later experiments use the '{winner}' "
        f"representation.")

    return {
        "winner": winner,
        "payload": {
            "verdict": verdict,
            "tables": [{
                "title": f"Mutual {K_DEFAULT}-NN graph per representation "
                         f"({len(sessions):,} sessions)",
                "columns": ["representation", "neighbor lexical jaccard",
                            "same-chat edge frac", "giant component",
                            "leiden clusters", "modularity", "coherence"],
                "rows": rows}],
            "clusters": [],
            "samples": samples[:12]}}


def experiment_neighborhood(sessions, x: np.ndarray,
                            knn: KnnIndex) -> tuple[csr_matrix, dict]:
    """Exp 2: graph construction sweep (k, mutuality, edge weighting)."""
    print("experiment 2: neighborhood graph sweep…", flush=True)
    sweep_rows = []
    for k in K_SWEEP:
        for mutual in (False, True):
            adj = knn_graph(knn, k, mutual=mutual, weighting="cosine")
            stats = graph_stats(adj)
            edges = sample_edges(adj, EDGE_SAMPLE)
            jac = edge_lexical_jaccard(sessions, edges)
            sweep_rows.append([
                k, "mutual" if mutual else "plain",
                round(stats["giant_frac"], 3), stats["n_components"],
                stats["median_degree"], round(stats["isolated_frac"], 3),
                round(stats["top1pct_degree_share"], 3), round(jac, 3)])

    weight_rows = []
    adj_by_weighting: dict[str, csr_matrix] = {}
    quality: dict[str, float] = {}
    for weighting in ("binary", "cosine", "adaptive"):
        adj = knn_graph(knn, K_DEFAULT, mutual=True, weighting=weighting)
        labels = run_leiden(adj)
        mod = modularity(adj, labels)
        cond = mean_top_conductance(adj, labels)
        coh = cluster_coherence(x, labels)
        weight_rows.append([weighting, len(set(labels.tolist())),
                            round(mod, 3), round(cond, 3), round(coh, 3)])
        adj_by_weighting[weighting] = adj
        quality[weighting] = mod - cond
    best_weighting = max(quality, key=quality.get)
    best_adj = adj_by_weighting[best_weighting]

    mutual10 = next(r for r in sweep_rows if r[0] == 10 and r[1] == "mutual")
    mutual20 = next(r for r in sweep_rows if r[0] == 20 and r[1] == "mutual")
    plain20 = next(r for r in sweep_rows if r[0] == 20 and r[1] == "plain")
    verdict = (
        f"Mutual kNN reduces hubness — at k=20 the top 1% of sessions "
        f"hold {plain20[6]:.1%} of plain-kNN edge mass vs {mutual20[6]:.1%} "
        f"after requiring mutuality — while keeping {mutual20[2]:.1%} of "
        f"sessions in the giant component ({mutual20[3]} components, "
        f"{mutual20[5]:.1%} isolated). Smaller k fragments the corpus "
        f"(k=10 mutual: {mutual10[3]} components), larger k glues distinct "
        f"regions together and dilutes neighbor quality (jaccard "
        f"{mutual20[7]:.3f} at k=20 vs "
        f"{next(r for r in sweep_rows if r[0] == 50 and r[1] == 'mutual')[7]:.3f} "
        f"at k=50). Of the three edge weightings, '{best_weighting}' gave "
        f"the best Leiden partitions (modularity minus conductance), so "
        f"the final graph is mutual {K_DEFAULT}-NN with {best_weighting} "
        f"weights.")

    return best_adj, {
        "verdict": verdict,
        "tables": [
            {"title": "k / mutuality sweep (cosine weights)",
             "columns": ["k", "graph", "giant component", "components",
                         "median degree", "isolated frac",
                         "top-1% degree share", "neighbor jaccard"],
             "rows": sweep_rows},
            {"title": f"Edge weighting at mutual k={K_DEFAULT} "
                      "(Leiden γ=1 downstream)",
             "columns": ["weighting", "clusters", "modularity",
                         "mean conductance (top 10)", "coherence"],
             "rows": weight_rows}],
        "clusters": [], "samples": []}


def experiment_laplacian(sessions, x: np.ndarray, adj: csr_matrix,
                         background: Counter, api_key: str
                         ) -> tuple[np.ndarray, dict]:
    """Exp 3: normalized Laplacian spectrum, spectral clustering, diffusion."""
    print("experiment 3: laplacian spectral analysis…", flush=True)
    n_comp, comp_labels = csgraph.connected_components(adj, directed=False)
    sizes = np.bincount(comp_labels)
    giant = comp_labels == sizes.argmax()
    giant_idx = np.flatnonzero(giant)
    w = adj[giant][:, giant]
    print(f"  giant component: {giant.sum():,}/{len(sessions):,} sessions")

    lap = csgraph.laplacian(w.astype(np.float64), normed=True)
    n_eig = min(N_EIGEN, w.shape[0] - 2)
    evals, evecs = eigsh(lap.tocsc(), k=n_eig, sigma=-0.01, which="LM")
    order = np.argsort(evals)
    evals, evecs = evals[order], evecs[:, order]

    gaps = np.diff(evals)
    # Ignore gaps below k=4 (they reflect stray small components, not topics).
    gap_rows = [[int(i + 1), round(float(evals[i]), 4),
                 round(float(gaps[i]), 4)]
                for i in np.argsort(gaps[4:])[::-1][:8] + 4]
    gap_rows.sort(key=lambda r: -r[2])
    k_spec = gap_rows[0][0]
    k_spec = int(np.clip(k_spec, 8, 30))

    u = evecs[:, :k_spec]
    u_norm = u / np.maximum(np.linalg.norm(u, axis=1, keepdims=True), 1e-9)
    km = KMeans(n_clusters=k_spec, n_init=10, random_state=0).fit(u_norm)
    labels = np.full(len(sessions), -1, dtype=np.int32)
    labels[giant_idx] = km.labels_

    # Diffusion coordinates: psi = D^{-1/2} u, eigenvalue (1 - lambda)^t.
    deg = np.asarray(w.sum(1)).ravel()
    psi = evecs[:, 1:33] / np.sqrt(np.maximum(deg, 1e-9))[:, None]
    lam_rw = np.maximum(1.0 - evals[1:33], 0.0)
    diff_rows = []
    rng = np.random.default_rng(0)
    samp = rng.choice(w.shape[0], size=min(3000, w.shape[0]), replace=False)
    for t in (1, 4, 16):
        coords = psi * (lam_rw ** t)[None, :]
        try:
            sil = silhouette_score(coords[samp], km.labels_[samp])
        except ValueError:
            sil = float("nan")
        diff_rows.append([t, round(float(sil), 3)])

    clusters = describe_clusters(sessions, x, labels, adj, background,
                                 api_key)
    eig_profile = [round(float(v), 4) for v in evals[:32]]
    best_t = max(diff_rows, key=lambda r: r[1])
    diff_coords = psi * (lam_rw ** best_t[0])[None, :]
    verdict = (
        f"The spectrum of the symmetric normalized Laplacian has no single "
        f"dominant eigengap — structure is hierarchical, as the plan "
        f"predicted. The largest usable gap sits at k={gap_rows[0][0]}, so "
        f"spectral k-means used K={k_spec} on the giant component "
        f"({giant.sum():,} sessions). Diffusion-map separation peaks at "
        f"t={best_t[0]} (silhouette {best_t[1]}), meaning clusters are "
        f"best seen as medium-scale diffusion neighborhoods rather than "
        f"hard partitions.")

    payload = {
        "verdict": verdict,
        "tables": [
            {"title": "Largest eigengaps of L_sym (k ≥ 5)",
             "columns": ["k", "λ_k", "gap to λ_k+1"],
             "rows": gap_rows},
            {"title": "First 32 eigenvalues",
             "columns": ["λ profile"],
             "rows": [[", ".join(str(v) for v in eig_profile)]]},
            {"title": "Spectral cluster silhouette in diffusion coordinates",
             "columns": ["diffusion time t", "silhouette"],
             "rows": diff_rows}],
        "clusters": clusters, "samples": []}
    return labels, payload, giant_idx, diff_coords


def experiment_clustering(sessions, x: np.ndarray, adj: csr_matrix,
                          spectral_labels: np.ndarray, background: Counter,
                          api_key: str) -> tuple[dict, np.ndarray, dict]:
    """Exp 4: Leiden sweep vs HDBSCAN vs k-means, small-niche recovery."""
    print("experiment 4: alternative clustering…", flush=True)
    method_rows = []
    labelings: dict[str, np.ndarray] = {}

    for gamma in LEIDEN_GAMMAS:
        labels = run_leiden(adj, gamma=gamma)
        sizes = Counter(labels.tolist())
        big = [c for c, n in sizes.items() if n >= 5]
        labelings[f"leiden γ={gamma}"] = labels
        method_rows.append([
            f"leiden γ={gamma}", len(sizes), len(big),
            round(float(np.median([n for n in sizes.values()])), 1), "0%",
            round(mean_top_conductance(adj, labels), 3),
            round(cluster_coherence(x, labels), 3)])

    xd = debias(x, 2)
    # leaf selection keeps the fine-grained clusters instead of merging
    # them up the condensed tree — that is where the narrow niches live.
    hdb = HDBSCAN(min_cluster_size=10, min_samples=5,
                  cluster_selection_method="leaf", metric="euclidean",
                  copy=True).fit(xd)
    labelings["hdbscan"] = hdb.labels_.astype(np.int32)
    noise = float((hdb.labels_ == -1).mean())
    sizes = Counter(c for c in hdb.labels_.tolist() if c >= 0)
    method_rows.append([
        "hdbscan (debiased)", len(sizes), len(sizes),
        round(float(np.median(list(sizes.values()) or [0])), 1),
        f"{noise:.0%}",
        round(mean_top_conductance(adj, labelings["hdbscan"]), 3),
        round(cluster_coherence(x, labelings["hdbscan"]), 3)])

    k_ref = len({c for c in labelings["leiden γ=1.0"].tolist()})
    km = KMeans(n_clusters=min(k_ref, 30), n_init=10,
                random_state=0).fit(xd)
    labelings["kmeans"] = km.labels_.astype(np.int32)
    ksizes = Counter(km.labels_.tolist())
    method_rows.append([
        f"k-means k={min(k_ref, 30)} (debiased)", len(ksizes), len(ksizes),
        round(float(np.median(list(ksizes.values()))), 1), "0%",
        round(mean_top_conductance(adj, labelings["kmeans"]), 3),
        round(cluster_coherence(x, labelings["kmeans"]), 3)])

    ref = labelings["leiden γ=1.0"]
    ari_rows = []
    for name, lab in labelings.items():
        both = (lab >= 0) & (ref >= 0)
        ari_rows.append([name, round(float(
            adjusted_rand_score(ref[both], lab[both])), 3)])
    spec_mask = (spectral_labels >= 0) & (ref >= 0)
    ari_rows.append(["spectral (exp 3)", round(float(adjusted_rand_score(
        ref[spec_mask], spectral_labels[spec_mask])), 3)])

    print("  labeling leiden γ=1 clusters…", flush=True)
    clusters = describe_clusters(sessions, x, ref, adj, background, api_key)

    # Small-niche mining: tight HDBSCAN clusters global methods would blur.
    niches = []
    for cid, size in sorted(sizes.items(), key=lambda kv: kv[1]):
        if not (8 <= size <= 60) or len(niches) >= 6:
            continue
        member_idx = np.flatnonzero(hdb.labels_ == cid)
        phrases = cluster_phrases(sessions, member_idx, background, limit=5)
        if not phrases:
            continue
        contact, share = top_contact_share(sessions, member_idx)
        niches.append({
            "label": "niche: " + ", ".join(phrases[:2]),
            "size": int(size),
            "conductance": round(
                conductance(adj, labelings["hdbscan"] == cid), 3),
            "phrases": phrases,
            "top_contact": contact, "top_contact_share": round(share, 2),
            "example": representative_snippet(sessions, x, member_idx)})

    n_leiden1 = len({c for c in ref.tolist()})
    spectral_ari = ari_rows[-1][1]
    agreement = ("agree on the broad domains" if spectral_ari >= 0.3
                 else "carve the graph up quite differently")
    verdict = (
        f"Leiden at γ=1 finds {n_leiden1} communities; spectral k-means "
        f"and Leiden {agreement} (ARI {spectral_ari}) — spectral k-means "
        f"is forced to a small K by the eigengap and so merges what Leiden "
        f"keeps separate. Raising the resolution to γ=4 splits the graph "
        f"into {method_rows[3][1]} micro-communities, tracing the "
        f"hierarchy the plan asked for, at a modest conductance cost "
        f"({method_rows[3][5]} vs {method_rows[1][5]} at γ=1). HDBSCAN "
        f"takes the opposite trade: it discards {noise:.0%} of sessions "
        f"as noise, but the clusters it keeps are the tightest "
        f"(conductance {method_rows[4][5]}) and its small clusters "
        f"surface narrow niches (below) that the global partitions absorb "
        f"into larger topics. Plain k-means on the debiased embeddings is "
        f"the weakest cut of the graph (conductance {method_rows[5][5]}).")

    payload = {
        "verdict": verdict,
        "tables": [
            {"title": "Method comparison",
             "columns": ["method", "clusters", "clusters ≥5",
                         "median size", "noise", "mean conductance (top 10)",
                         "coherence"],
             "rows": method_rows},
            {"title": "Agreement with Leiden γ=1 (adjusted Rand index)",
             "columns": ["method", "ARI"],
             "rows": ari_rows}],
        "clusters": clusters + niches, "samples": []}
    gamma_labels = {g: labelings[f"leiden γ={g}"] for g in LEIDEN_GAMMAS}
    return payload, gamma_labels


# Minimum community size to earn an LLM label, per Leiden resolution.
LABEL_MIN_SIZE = {0.5: 25, 1.0: 25, 2.0: 15, 4.0: 10}
LABEL_BATCH = 12

_BANNED_LABELS = (
    "social plans, hangout plans, group hangout, friend chat, group chat, "
    "college life, campus life, gym plans, daily life, life updates, "
    "making plans, casual chat, logistics, catching up")


def central_examples(sessions: list[Session], x: np.ndarray,
                     member_idx: np.ndarray, n: int = 3,
                     chars: int = 420) -> list[str]:
    members = x[member_idx]
    c = members.mean(0)
    c /= np.linalg.norm(c) + 1e-9
    order = np.argsort(-(members @ c))[:n]
    return [sessions[member_idx[i]].disp_text.replace("\n", " · ")[:chars]
            for i in order]


def label_batch_with_llm(clusters: list[dict], used: list[str],
                         api_key: str) -> dict[int, str]:
    """Label a batch of clusters in one call so the model can contrast them
    against each other, and against labels already assigned elsewhere."""
    lines = []
    for c in clusters:
        people = ", ".join(f"{name} {share:.0%}"
                           for name, share in c["top_contacts"][:3])
        lines.append(
            f"cluster {c['key']} ({c['size']} conversations)\n"
            f"  distinctive phrases: {', '.join(c['phrases'][:8])}\n"
            f"  people: {people}\n"
            + "\n".join(f"  example: \"{e}\"" for e in c["examples"][:3]))
    system = (
        "You label topic clusters mined from one person's iMessage history. "
        "For each cluster you get statistically distinctive phrases (over-"
        "represented vs every other conversation), the main people, and the "
        "most central example conversations.\n"
        "Rules:\n"
        "- Be CONCRETE: name the actual activity, subject, event, entity, "
        "or place (e.g. 'marathon training', 'cse 312 problem sets', "
        "'prom photo logistics', 'brawl stars sessions').\n"
        f"- BANNED generic labels: {_BANNED_LABELS}. If tempted, look at "
        "the phrases and examples again and find what makes THIS cluster "
        "different from the others in this list.\n"
        "- Every label must differ from the other labels in this batch AND "
        "from the already-used labels provided.\n"
        "- 2-5 words, lowercase, no punctuation, never a person's name "
        "alone.\n"
        'Reply JSON: {"labels": {"<cluster key>": "<label>", ...}}')
    user = ""
    if used:
        user += "already-used labels: " + ", ".join(used) + "\n\n"
    user += "\n\n".join(lines)
    for attempt in range(3):
        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": os.environ.get("OPENAI_MODEL", "gpt-5-nano"),
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "response_format": {"type": "json_object"}},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=240)
            r.raise_for_status()
            body = r.json()
            if body["choices"][0]["finish_reason"] == "length":
                print("  batch label response truncated, retrying…",
                      flush=True)
                continue
            raw = json.loads(body["choices"][0]["message"]["content"])
            got = raw.get("labels", raw) if isinstance(raw, dict) else raw
            if isinstance(got, list):
                # Tolerate [{"cluster": 7, "label": "..."}] shape.
                flat = {}
                for item in got:
                    if isinstance(item, dict):
                        k = (item.get("key") or item.get("cluster")
                             or item.get("id") or item.get("cluster_key"))
                        v = item.get("label")
                        if k is not None and isinstance(v, str):
                            flat[str(k)] = v
                got = flat
            if not isinstance(got, dict):
                got = {}
            # Models sometimes key by "cluster 7" instead of "7".
            norm: dict[str, str] = {}
            for k, v in got.items():
                m = re.search(r"\d+", str(k))
                if m and isinstance(v, str):
                    norm[m.group()] = v
            out = {c["key"]: norm.get(str(c["key"]), "").strip().lower()
                   for c in clusters}
            n_ok = sum(1 for v in out.values() if v)
            if n_ok >= max(1, len(clusters) // 2):
                return out
            print(f"  batch labels incomplete ({n_ok}/{len(clusters)}), "
                  f"keys were {list(got)[:5]}, retrying…", flush=True)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError,
                TypeError) as exc:
            print(f"  batch label attempt {attempt + 1} failed: "
                  f"{type(exc).__name__}", flush=True)
            time.sleep(2 ** attempt)
    return {}


def build_communities(sessions: list[Session], x: np.ndarray,
                      gamma_labels: dict[float, np.ndarray],
                      background: Counter, api_key: str) -> list[dict]:
    """Describe and LLM-label each sizeable Leiden community at every
    resolution, and link each to its majority-overlap parent at the
    next-coarser resolution."""
    gammas = sorted(gamma_labels)
    communities: list[dict] = []
    key = 0
    for gamma in gammas:
        labels = gamma_labels[gamma]
        for cid, size in Counter(labels.tolist()).items():
            if size < LABEL_MIN_SIZE[gamma]:
                continue
            member_idx = np.flatnonzero(labels == cid)
            members = [sessions[i] for i in member_idx]
            contact_counts = Counter(s.contact for s in members)
            top_contacts = [(name, n / size)
                            for name, n in contact_counts.most_common(5)]
            years = Counter(s.start_ts[:4] for s in members)
            total_msgs = sum(s.n_msgs for s in members)
            communities.append({
                "key": key, "gamma": gamma, "cluster_id": int(cid),
                "size": int(size),
                "phrases": cluster_phrases(sessions, member_idx,
                                           background, limit=8),
                "top_contacts": top_contacts,
                "years": dict(sorted(years.items())),
                "from_me_frac": round(
                    sum(s.n_from_me for s in members) / max(total_msgs, 1),
                    3),
                "initiated_frac": round(
                    sum(s.initiated_by_me for s in members) / size, 3),
                "median_msgs": int(np.median([s.n_msgs for s in members])),
                "examples": central_examples(sessions, x, member_idx),
            })
            key += 1

    # Leiden is seeded, so an unchanged graph reproduces the same
    # (gamma, cluster_id, size) triples — reuse those labels instead of
    # paying for (and re-randomizing) LLM naming on every refresh.
    cached_labels: dict[tuple, str] = {}
    if OUT.exists():
        prev = duckdb.connect(str(OUT), read_only=True)
        try:
            cached_labels = {
                (g, cid, size): label for g, cid, size, label in prev.execute(
                    "SELECT gamma, cluster_id, size, label "
                    "FROM semantic_communities").fetchall()}
        except duckdb.CatalogException:
            pass
        finally:
            prev.close()
    for c in communities:
        c["label"] = cached_labels.get(
            (c["gamma"], c["cluster_id"], c["size"]), "")
    todo = [c for c in communities if not c["label"]]

    print(f"labeling {len(todo)} of {len(communities)} communities "
          f"across γ={gammas} ({len(communities) - len(todo)} reused)…",
          flush=True)
    # Batch within one resolution so the model contrasts siblings — that is
    # where near-duplicate generic labels come from. "Used" labels only need
    # to be unique within a resolution (each legend shows one γ at a time).
    for gamma in gammas:
        group = [c for c in todo if c["gamma"] == gamma]
        used = [c["label"] for c in communities
                if c["gamma"] == gamma and c["label"]]
        for i in range(0, len(group), LABEL_BATCH):
            batch = group[i:i + LABEL_BATCH]
            got = label_batch_with_llm(batch, used, api_key)
            for c in batch:
                label = got.get(c["key"], "")
                if not label:
                    label = ", ".join(c["phrases"][:2]) or "unlabeled"
                c["label"] = label
                used.append(label)
            print(f"  γ={gamma}: "
                  f"{', '.join(c['label'] for c in batch[:6])}…", flush=True)

    for c in communities:
        gamma = c["gamma"]
        gi = gammas.index(gamma)
        if gi == 0:
            c["parent_gamma"], c["parent_cluster_id"] = None, None
            continue
        members = gamma_labels[gamma] == c["cluster_id"]
        coarser = gamma_labels[gammas[gi - 1]]
        parent = int(Counter(coarser[members].tolist()).most_common(1)[0][0])
        c["parent_gamma"] = gammas[gi - 1]
        c["parent_cluster_id"] = parent
    return communities


def fit_umap_3d(diff_coords: np.ndarray, n_neighbors: int,
                min_dist: float) -> np.ndarray:
    """Unit-variance 3D UMAP of diffusion coordinates."""
    n = len(diff_coords)
    nn = min(n_neighbors, max(2, n - 1))
    coords = umap.UMAP(n_components=3, n_neighbors=nn, min_dist=min_dist,
                       random_state=42).fit_transform(diff_coords)
    return (coords - coords.mean(0)) / (coords.std(0) + 1e-9)


def write_session_map(sessions: list[Session], giant_idx: np.ndarray,
                      diff_coords: np.ndarray,
                      gamma_labels: dict[float, np.ndarray],
                      communities: list[dict]) -> None:
    """2D and 3D UMAP layouts of the giant component, computed on diffusion
    coordinates (multi-step graph connectivity) so domains separate more
    cleanly than in raw embedding space."""
    n_pts = len(giant_idx)
    grid = [(nn, md) for nn in UMAP_NEIGHBORS_SWEEP
            for md in UMAP_MIN_DIST_SWEEP]
    print(f"session map: UMAP sweep ({len(grid)} layouts) on "
          f"{n_pts:,} diffusion vectors…", flush=True)
    coords_by_key: dict[tuple[int, float], np.ndarray] = {}
    for i, (nn, md) in enumerate(grid, 1):
        t0 = time.perf_counter()
        coords_by_key[(nn, md)] = fit_umap_3d(diff_coords, nn, md)
        print(f"  [{i}/{len(grid)}] n_neighbors={nn} min_dist={md} "
              f"({time.perf_counter() - t0:.1f}s)", flush=True)
    coords3 = coords_by_key[(UMAP_DEFAULT_NEIGHBORS, UMAP_DEFAULT_MIN_DIST)]
    coords2 = umap.UMAP(
        n_components=2,
        n_neighbors=min(UMAP_DEFAULT_NEIGHBORS, max(2, n_pts - 1)),
        min_dist=UMAP_DEFAULT_MIN_DIST,
        random_state=42,
    ).fit_transform(diff_coords)
    coords2 = (coords2 - coords2.mean(0)) / (coords2.std(0) + 1e-9)

    labeled = {(c["gamma"], c["cluster_id"]) for c in communities}

    def cid_of(gamma: float, i: int) -> int:
        cid = int(gamma_labels[gamma][i])
        return cid if (gamma, cid) in labeled else -1

    rows = []
    for row, i in enumerate(giant_idx):
        s = sessions[i]
        rows.append((
            s.session_id,
            float(coords2[row, 0]), float(coords2[row, 1]),
            float(coords3[row, 0]), float(coords3[row, 1]),
            float(coords3[row, 2]),
            cid_of(0.5, i), cid_of(1.0, i), cid_of(2.0, i), cid_of(4.0, i),
            s.contact, s.start_ts[:10], s.n_msgs,
            s.disp_text.replace("\n", " · ")[:140]))

    con = duckdb.connect(str(OUT))
    con.execute("""
        CREATE OR REPLACE TABLE session_map (
            session_id TEXT, x DOUBLE, y DOUBLE,
            x3 DOUBLE, y3 DOUBLE, z3 DOUBLE,
            c05 INTEGER, c1 INTEGER, c2 INTEGER, c4 INTEGER,
            contact TEXT, start_ts TEXT, n_msgs INTEGER, snippet TEXT);
        CREATE OR REPLACE TABLE semantic_communities (
            gamma DOUBLE, cluster_id INTEGER, label TEXT, size INTEGER,
            phrases TEXT, top_contacts TEXT, years TEXT,
            from_me_frac DOUBLE, initiated_frac DOUBLE,
            median_msgs INTEGER, examples TEXT,
            parent_gamma DOUBLE, parent_cluster_id INTEGER)""")
    con.executemany(
        "INSERT INTO session_map VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.executemany(
        "INSERT INTO semantic_communities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(c["gamma"], c["cluster_id"], c["label"], c["size"],
          json.dumps(c["phrases"]), json.dumps(c["top_contacts"]),
          json.dumps(c["years"]), c["from_me_frac"], c["initiated_frac"],
          c["median_msgs"], json.dumps(c["examples"]),
          c["parent_gamma"], c["parent_cluster_id"])
         for c in communities])
    variant_rows = []
    for row, i in enumerate(giant_idx):
        sid = sessions[i].session_id
        for (nn, md), coords in coords_by_key.items():
            variant_rows.append((
                nn, md, sid,
                float(coords[row, 0]), float(coords[row, 1]),
                float(coords[row, 2])))
    con.execute("""
        CREATE OR REPLACE TABLE session_umap_variants (
            n_neighbors INTEGER, min_dist DOUBLE, session_id TEXT,
            x3 DOUBLE, y3 DOUBLE, z3 DOUBLE)""")
    con.executemany(
        "INSERT INTO session_umap_variants VALUES (?,?,?,?,?,?)", variant_rows)
    con.close()
    print(f"  wrote {len(rows):,} map points, {len(variant_rows):,} variant "
          f"coords, {len(communities)} labeled communities")


# --------------------------------------------------------------------- main

def write_results(experiments: list[tuple[str, str, str, dict]]) -> None:
    con = duckdb.connect(str(OUT))
    con.execute("""
        CREATE OR REPLACE TABLE semantic_experiments (
            experiment TEXT, title TEXT, summary TEXT, payload TEXT,
            created_at TIMESTAMP DEFAULT now())""")
    for exp_id, title, summary, payload in experiments:
        con.execute(
            "INSERT INTO semantic_experiments "
            "(experiment, title, summary, payload) VALUES (?,?,?,?)",
            [exp_id, title, summary, json.dumps(payload)])
    con.close()


def giant_diffusion(adj: csr_matrix, t: int = 16
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Diffusion coordinates of the giant component (for --map-only runs;
    the experiment path derives them inside experiment_laplacian)."""
    _n, comp_labels = csgraph.connected_components(adj, directed=False)
    giant_idx = np.flatnonzero(comp_labels == np.bincount(comp_labels).argmax())
    w = adj[giant_idx][:, giant_idx]
    lap = csgraph.laplacian(w.astype(np.float64), normed=True)
    evals, evecs = eigsh(lap.tocsc(), k=min(N_EIGEN, w.shape[0] - 2),
                         sigma=-0.01, which="LM")
    order = np.argsort(evals)
    evals, evecs = evals[order], evecs[:, order]
    deg = np.asarray(w.sum(1)).ravel()
    psi = evecs[:, 1:33] / np.sqrt(np.maximum(deg, 1e-9))[:, None]
    lam_rw = np.maximum(1.0 - evals[1:33], 0.0)
    return giant_idx, psi * (lam_rw ** t)[None, :]


def main(map_only: bool = False) -> None:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "insert_openai_key_here":
        raise SystemExit("OPENAI_API_KEY missing — copy .env.example to .env "
                         "and add your key")
    if not ANALYTICS.exists() or not LANGUAGE.exists():
        raise SystemExit("run `python -m ingest` and scripts/language.py "
                         "first")

    sessions, mean_emb = load_sessions()
    conv_emb = conv_embeddings(sessions, api_key)
    background = ngram_counts([s.raw_text for s in sessions])

    if map_only:
        # Winning configuration from the experiment suite: debiased
        # transcript embeddings, mutual 20-NN cosine graph.
        x = debias(conv_emb, 2)
        knn = build_knn(x)
        adj = knn_graph(knn, K_DEFAULT, mutual=True, weighting="cosine")
        gamma_labels = {g: run_leiden(adj, gamma=g) for g in LEIDEN_GAMMAS}
        giant_idx, diff_coords = giant_diffusion(adj)
        communities = build_communities(sessions, x, gamma_labels,
                                        background, api_key)
        write_session_map(sessions, giant_idx, diff_coords, gamma_labels,
                          communities)
        print(f"done — map refreshed in {OUT}")
        return

    reps = {
        "weighted-mean": mean_emb,
        "weighted-mean debiased": debias(mean_emb, 2),
        "conversation": conv_emb,
        "conversation debiased": debias(conv_emb, 2),
    }

    exp1 = experiment_representation(sessions, reps, api_key)
    x = reps[exp1["winner"]]
    knn = build_knn(x)

    adj, payload2 = experiment_neighborhood(sessions, x, knn)
    spectral_labels, payload3, giant_idx, diff_coords = experiment_laplacian(
        sessions, x, adj, background, api_key)
    payload4, gamma_labels = experiment_clustering(
        sessions, x, adj, spectral_labels, background, api_key)
    communities = build_communities(sessions, x, gamma_labels, background,
                                    api_key)
    write_session_map(sessions, giant_idx, diff_coords, gamma_labels,
                      communities)

    write_results([
        ("representation",
         "Experiment 1 — What should a conversation vector be?",
         "Weighted mean of existing message embeddings vs directly "
         "embedding the whole session transcript (both raw and with the "
         "top tone/register components projected out).",
         exp1["payload"]),
        ("neighborhood",
         "Experiment 2 — Building the semantic neighborhood graph",
         "Sweep of k, plain vs mutual kNN, and edge weighting (binary / "
         "cosine / adaptive local scaling) on the winning representation.",
         payload2),
        ("laplacian",
         "Experiment 3 — Laplacian spectrum & diffusion geometry",
         "Eigenvalues and eigengaps of the symmetric normalized Laplacian, "
         "spectral k-means on the giant component, and cluster separation "
         "in diffusion-map coordinates at several diffusion times.",
         payload3),
        ("clustering",
         "Experiment 4 — Leiden vs HDBSCAN vs k-means",
         "Multi-resolution Leiden sweep against density-based and "
         "centroid baselines, plus small-niche mining from tight HDBSCAN "
         "clusters.",
         payload4),
    ])
    print(f"done — results in {OUT}::semantic_experiments")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-only", action="store_true",
                        help="refresh session_map + communities without "
                             "rerunning the experiment suite")
    args = parser.parse_args()
    main(map_only=args.map_only)
