"""Build data/language.duckdb: OpenAI embeddings, topic clusters, voice metrics,
and distinctive signature phrases. Run after `python -m ingest`:

    uv run python scripts/language.py
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import httpx
import numpy as np
import umap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.phrases import log_odds, ngram_counts
from server.llm import load_env_file

ANALYTICS = Path("data/analytics.duckdb")
OUT = Path("data/language.duckdb")
EMBED_MODEL = "text-embedding-3-small"
DIMS = 256
BATCH = 1000
K_CLUSTERS = 14
TOP_PERSONS_VOICE = 30
TOP_PERSONS_PHRASES = 20


def embed_texts(texts: list[str], api_key: str) -> np.ndarray:
    out = np.empty((len(texts), DIMS), dtype=np.float32)
    for start in range(0, len(texts), BATCH):
        batch = [t[:300] for t in texts[start:start + BATCH]]
        for attempt in range(4):
            try:
                r = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    json={"model": EMBED_MODEL, "input": batch,
                          "dimensions": DIMS},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=120,
                )
                r.raise_for_status()
                break
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                print(f"  retry {attempt + 1} after {type(exc).__name__}, "
                      f"sleeping {wait}s", flush=True)
                time.sleep(wait)
        for item in r.json()["data"]:
            out[start + item["index"]] = item["embedding"]
        done = min(start + BATCH, len(texts))
        if (start // BATCH) % 20 == 0 or done == len(texts):
            print(f"  embedded {done:,}/{len(texts):,}", flush=True)
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(norms, 1e-9)


def kmeans(x: np.ndarray, k: int, iters: int = 25, seed: int = 0):
    rng = np.random.default_rng(seed)
    centroids = [x[rng.integers(len(x))]]
    for _ in range(k - 1):
        dist = np.min(np.stack([1 - x @ c for c in centroids]), axis=0)
        dist = np.maximum(dist, 0) ** 2
        centroids.append(x[rng.choice(len(x), p=dist / dist.sum())])
    c = np.stack(centroids)
    assign = np.zeros(len(x), dtype=np.int32)
    for _ in range(iters):
        assign = (x @ c.T).argmax(1)
        for j in range(k):
            members = x[assign == j]
            if len(members):
                c[j] = members.mean(0)
                c[j] /= np.linalg.norm(c[j]) + 1e-9
    return assign, c


def _silhouette(x: np.ndarray, assign: np.ndarray, k: int) -> float:
    d = 1 - x @ x.T
    scores = []
    for i in range(len(x)):
        same = assign == assign[i]
        same[i] = False
        if not same.any():
            continue
        a = d[i][same].mean()
        others = [d[i][assign == j].mean()
                  for j in range(k) if j != assign[i] and (assign == j).any()]
        if not others:
            continue
        b = min(others)
        scores.append((b - a) / max(a, b, 1e-12))
    return float(np.mean(scores)) if scores else -1.0


def pick_kmeans(x: np.ndarray, k_range=range(3, 9)):
    """Run k-means for each k and keep the k with the best silhouette score."""
    best = None
    for k in k_range:
        if k >= len(x):
            break
        assign, cent = kmeans(x, k, seed=42)
        score = _silhouette(x, assign, k)
        if best is None or score > best[3]:
            best = (assign, cent, k, score)
    if best is None:
        raise ValueError("not enough points to cluster")
    return best[0], best[1], best[2]


def label_cluster(samples: list[str], api_key: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        json={"model": os.environ.get("OPENAI_MODEL", "gpt-5-nano"),
              "messages": [
                  {"role": "system",
                   "content": "You name topic clusters of casual text messages. "
                              'Reply with JSON {"label": "2-4 word label"}. '
                              "Be concrete, lowercase, no punctuation."},
                  {"role": "user", "content": "\n".join(samples)},
              ],
              "response_format": {"type": "json_object"}},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=90,
    )
    r.raise_for_status()
    try:
        return json.loads(r.json()["choices"][0]["message"]["content"])["label"]
    except (KeyError, json.JSONDecodeError):
        return "misc"


def cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def weighted_centroid(emb: np.ndarray, idx: list[int], weights: list[int]):
    if not idx:
        return None
    w = np.asarray(weights, dtype=np.float32)
    c = (emb[idx] * w[:, None]).sum(0) / w.sum()
    n = np.linalg.norm(c)
    return c / n if n > 1e-9 else None


def main() -> None:
    load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY missing — add it to .env")
    if not ANALYTICS.exists():
        raise SystemExit("data/analytics.duckdb missing — run `python -m ingest`")

    con = duckdb.connect(str(ANALYTICS), read_only=True)
    msgs = con.execute("""
        SELECT trim(m.text) AS t, m.is_from_me, m.person_id,
               strftime(date_trunc('month', m.ts_local), '%Y-%m') AS month,
               strftime(date_trunc('year', m.ts_local), '%Y') AS year,
               NOT c.is_group AS is_dm
        FROM messages m JOIN chats c ON c.chat_id = m.chat_id
        WHERE m.text IS NOT NULL AND len(trim(m.text)) > 0""").fetchall()
    person_names = dict(con.execute(
        "SELECT person_id, display_name FROM persons "
        "WHERE display_name NOT LIKE 'urn:%'").fetchall())
    top_voice = [r[0] for r in con.execute(f"""
        SELECT person_id FROM messages m
        JOIN chats c ON c.chat_id = m.chat_id AND NOT c.is_group
        WHERE person_id IS NOT NULL GROUP BY 1
        ORDER BY count(*) DESC LIMIT {TOP_PERSONS_VOICE}""").fetchall()
        if r[0] in person_names]
    con.close()
    print(f"{len(msgs):,} messages loaded")

    # ---- distinct texts + counts ----
    total_by_text: Counter = Counter()
    mine_by_text: Counter = Counter()
    for t, mine, _pid, _m, _y, _dm in msgs:
        total_by_text[t] += 1
        if mine:
            mine_by_text[t] += 1
    texts = list(total_by_text)
    text_idx = {t: i for i, t in enumerate(texts)}

    # Reuse embeddings from a previous run so re-runs only pay for new texts.
    cached: dict[str, int] = {}
    cached_emb = None
    if OUT.exists():
        prev = duckdb.connect(str(OUT), read_only=True)
        try:
            tbl = prev.execute(
                "SELECT text, embedding FROM text_embeddings").fetch_arrow_table()
            prev_texts = tbl["text"].to_pylist()
            cached_emb = np.asarray(
                tbl["embedding"].combine_chunks().flatten(),
                dtype=np.float32).reshape(len(prev_texts), DIMS)
            cached = {t: i for i, t in enumerate(prev_texts)}
            print(f"reusing {len(cached):,} cached embeddings")
        except duckdb.CatalogException:
            pass
        finally:
            prev.close()

    new_texts = [t for t in texts if t not in cached]
    print(f"{len(texts):,} distinct texts — {len(new_texts):,} to embed "
          f"with {EMBED_MODEL}")
    new_emb = (embed_texts(new_texts, api_key) if new_texts
               else np.empty((0, DIMS), dtype=np.float32))
    new_idx = {t: i for i, t in enumerate(new_texts)}
    emb = np.empty((len(texts), DIMS), dtype=np.float32)
    for t, i in text_idx.items():
        if t in cached:
            emb[i] = cached_emb[cached[t]]
        else:
            emb[i] = new_emb[new_idx[t]]

    # ---- topic clusters ----
    print("clustering…")
    assign, _ = kmeans(emb, K_CLUSTERS)
    cluster_msg_count: Counter = Counter()
    cluster_person: dict[int, Counter] = defaultdict(Counter)
    for t, _mine, pid, _m, _y, _dm in msgs:
        cid = int(assign[text_idx[t]])
        cluster_msg_count[cid] += 1
        if pid in person_names:
            cluster_person[cid][pid] += 1
    total_msgs = sum(cluster_msg_count.values())
    print("labeling clusters…")
    cluster_rows, cluster_people_rows = [], []
    for cid in range(K_CLUSTERS):
        members = [texts[i] for i in np.flatnonzero(assign == cid)]
        members.sort(key=lambda t: -total_by_text[t])
        label = label_cluster(members[:30], api_key)
        share = cluster_msg_count[cid] / total_msgs
        cluster_rows.append((cid, label, cluster_msg_count[cid], share))
        cluster_total = sum(cluster_person[cid].values()) or 1
        for pid, n in cluster_person[cid].most_common(3):
            cluster_people_rows.append(
                (cid, person_names[pid], n / cluster_total))
        print(f"  cluster {cid}: {label} ({share:.0%})")

    # ---- voice metrics ----
    print("voice metrics…")
    by_scope_texts: dict[tuple, Counter] = defaultdict(Counter)
    for t, mine, pid, month, _y, is_dm in msgs:
        if mine:
            by_scope_texts[("month", month)][t] += 1
            by_scope_texts[("me",)][t] += 1
            if is_dm and pid in person_names:
                by_scope_texts[("me_with", pid)][t] += 1
        elif is_dm and pid in person_names:
            by_scope_texts[("them", pid)][t] += 1

    def centroid(key) -> np.ndarray | None:
        c = by_scope_texts.get(key)
        if not c:
            return None
        idx = [text_idx[t] for t in c]
        return weighted_centroid(emb, idx, list(c.values()))

    me_global = centroid(("me",))
    voice_rows = []
    for pid in top_voice:
        me_p = centroid(("me_with", pid))
        them_p = centroid(("them", pid))
        if me_p is None or them_p is None or me_global is None:
            continue
        n = sum(by_scope_texts[("me_with", pid)].values())
        voice_rows.append((pid, person_names[pid], n,
                           1 - cos(me_p, me_global), cos(me_p, them_p)))

    months = sorted({k[1] for k in by_scope_texts if k[0] == "month"})
    drift_rows = []
    prev = None
    for m in months:
        if sum(by_scope_texts[("month", m)].values()) < 50:
            continue
        c = centroid(("month", m))
        if c is None:
            continue
        drift = 1 - cos(c, prev) if prev is not None else None
        novelty = 1 - cos(c, me_global) if me_global is not None else None
        drift_rows.append((m, drift, novelty))
        prev = c

    # ---- people clusters + temporal 3D map ----
    print("people clusters…")
    person_msg_texts: dict[int, Counter] = defaultdict(Counter)
    person_year_texts: dict[tuple[int, str], Counter] = defaultdict(Counter)
    for t, mine, pid, _m, year, _dm in msgs:
        if not mine and pid in person_names:
            person_msg_texts[pid][t] += 1
            person_year_texts[(pid, year)][t] += 1

    volumes = Counter({p: sum(c.values()) for p, c in person_msg_texts.items()})
    vec_all: dict[int, np.ndarray] = {}
    for pid, _n in volumes.most_common(40):
        c = person_msg_texts[pid]
        v = weighted_centroid(emb, [text_idx[t] for t in c], list(c.values()))
        if v is not None:
            vec_all[pid] = v
    pids = list(vec_all)
    people_x = np.stack([vec_all[p] for p in pids])
    assign_p, cent_p, k_p = pick_kmeans(people_x, range(3, 9))
    print(f"  {len(pids)} people → {k_p} clusters (best silhouette)")

    person_cluster_rows = []
    for cid in range(k_p):
        members = [pids[i] for i in range(len(pids)) if assign_p[i] == cid]
        samples = []
        for pid in members[:8]:
            tops = [t for t, _ in person_msg_texts[pid].most_common(80)
                    if len(t) >= 6][:6]
            samples += [f"{person_names[pid].split()[0]}: {t}" for t in tops]
        label = label_cluster(samples[:40], api_key)
        for pid in members:
            person_cluster_rows.append((cid, label, pid, person_names[pid]))
        print(f"  cluster {cid}: {label} — "
              f"{[person_names[p].split()[0] for p in members]}")

    period_keys: list[tuple[int, str]] = [(pid, "all") for pid in pids]
    period_vecs: list[np.ndarray] = [vec_all[pid] for pid in pids]
    period_msgs: dict[tuple[int, str], int] = {
        (pid, "all"): volumes[pid] for pid in pids}
    for (pid, year), c in sorted(person_year_texts.items()):
        if pid not in vec_all or sum(c.values()) < 30:
            continue
        v = weighted_centroid(emb, [text_idx[t] for t in c], list(c.values()))
        if v is None:
            continue
        period_keys.append((pid, year))
        period_vecs.append(v)
        period_msgs[(pid, year)] = sum(c.values())

    print(f"  UMAP on {len(period_vecs)} person-period vectors…")
    reducer = umap.UMAP(n_components=3, metric="cosine",
                        n_neighbors=min(10, len(period_vecs) - 1),
                        min_dist=0.3, random_state=42)
    coords = reducer.fit_transform(np.stack(period_vecs))
    coords = (coords - coords.mean(0)) / (coords.std(0) + 1e-9)

    person_map_rows = []
    for (pid, period), vec, (x, y, z) in zip(period_keys, period_vecs, coords):
        cid = int((vec @ cent_p.T).argmax())
        person_map_rows.append((pid, person_names[pid], period,
                                float(x), float(y), float(z), cid,
                                period_msgs[(pid, period)]))

    # ---- signature phrases (no embeddings needed) ----
    print("signature phrases…")
    global_all: Counter = Counter()
    global_mine: Counter = Counter()
    year_mine: dict[str, Counter] = defaultdict(Counter)
    pair_all: dict[int, Counter] = defaultdict(Counter)
    pair_volume: Counter = Counter()
    for t, mine, pid, _m, year, is_dm in msgs:
        grams = ngram_counts([t])
        global_all.update(grams)
        if mine:
            global_mine.update(grams)
            year_mine[year].update(grams)
        if is_dm and pid in person_names:
            pair_all[pid].update(grams)
            pair_volume[pid] += 1

    sig_rows = []
    others = global_all - global_mine
    for phrase, count, z in log_odds(global_mine, others, min_count=8, limit=25):
        sig_rows.append(("you", "You", phrase, count, z))
    for year, target in sorted(year_mine.items()):
        rest = global_mine - target
        for phrase, count, z in log_odds(target, rest, min_count=5, limit=15):
            sig_rows.append((f"year:{year}", year, phrase, count, z))
    for pid, _n in pair_volume.most_common(TOP_PERSONS_PHRASES):
        target = pair_all[pid]
        rest = global_all - target
        for phrase, count, z in log_odds(target, rest, min_count=4, limit=15):
            sig_rows.append((f"person:{pid}", person_names[pid],
                             phrase, count, z))

    # ---- write ----
    print("writing data/language.duckdb…")
    OUT.unlink(missing_ok=True)
    out = duckdb.connect(str(OUT))
    out.execute(f"""
        CREATE TABLE text_embeddings (
            text TEXT, total INTEGER, mine INTEGER, cluster_id INTEGER,
            embedding FLOAT[{DIMS}]);
        CREATE TABLE clusters (cluster_id INTEGER, label TEXT,
                               msg_count INTEGER, share DOUBLE);
        CREATE TABLE cluster_people (cluster_id INTEGER, name TEXT,
                                     share DOUBLE);
        CREATE TABLE voice_person (person_id INTEGER, name TEXT, msgs INTEGER,
                                   divergence DOUBLE, mirroring DOUBLE);
        CREATE TABLE voice_drift (month TEXT, drift DOUBLE, novelty DOUBLE);
        CREATE TABLE signature_phrases (scope TEXT, label TEXT, phrase TEXT,
                                        count INTEGER, score DOUBLE);
        CREATE TABLE person_clusters (cluster_id INTEGER, label TEXT,
                                      person_id INTEGER, name TEXT);
        CREATE TABLE person_map (person_id INTEGER, name TEXT, period TEXT,
                                 x DOUBLE, y DOUBLE, z DOUBLE,
                                 cluster_id INTEGER, msgs INTEGER);
    """)
    insert = f"INSERT INTO text_embeddings VALUES (?,?,?,?, CAST(? AS FLOAT[{DIMS}]))"
    chunk = 4000
    for start in range(0, len(texts), chunk):
        rows = [(t, total_by_text[t], mine_by_text[t],
                 int(assign[text_idx[t]]), emb[text_idx[t]].tolist())
                for t in texts[start:start + chunk]]
        out.executemany(insert, rows)
    out.executemany("INSERT INTO clusters VALUES (?,?,?,?)", cluster_rows)
    out.executemany("INSERT INTO cluster_people VALUES (?,?,?)",
                    cluster_people_rows)
    out.executemany("INSERT INTO voice_person VALUES (?,?,?,?,?)", voice_rows)
    out.executemany("INSERT INTO voice_drift VALUES (?,?,?)", drift_rows)
    out.executemany("INSERT INTO signature_phrases VALUES (?,?,?,?,?)", sig_rows)
    out.executemany("INSERT INTO person_clusters VALUES (?,?,?,?)",
                    person_cluster_rows)
    out.executemany("INSERT INTO person_map VALUES (?,?,?,?,?,?,?,?)",
                    person_map_rows)
    out.close()
    print(f"done: {len(texts):,} embeddings, {K_CLUSTERS} topics, "
          f"{len(voice_rows)} voice rows, {len(sig_rows)} signature phrases, "
          f"{k_p} people clusters, {len(person_map_rows)} map points")


if __name__ == "__main__":
    main()
