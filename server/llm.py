import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_CACHE_PATH = Path("data/llm_cache.json")
_SYSTEM_PROMPT = (
    "You summarize one day of a text-message conversation between the reader "
    "(their messages are labeled 'You') and one other person. Address the "
    "reader in the second person as 'you', and refer to the other person by "
    "the exact name used in the transcript labels — never 'Me' or 'the user', "
    "and never invent or substitute a different name. Reply with JSON: "
    '{"summary": "2-4 sentences: what was happening that day, the main topics, '
    'and the mood", "sentiment": "one or two words, e.g. warm, playful, tense, '
    'flirty, logistical"}. Be specific but concise; never invent details.'
)
_YOU_DAY_PROMPT = (
    "You summarize one day of the reader's text messages across several "
    "conversations. Their messages are labeled 'You'; everyone else is "
    "labeled by name, and each conversation is introduced with a header "
    "line. Address the reader in the second person as 'you' and refer to "
    "others by the exact names in the labels. Reply with JSON: "
    '{"summary": "3-5 sentences: what was happening that day across the '
    'conversations, the main topics, and the mood", "sentiment": "one or '
    'two words", "quotes": [3-5 standout messages copied VERBATIM from the '
    'transcript, each as {"speaker": "name or You", "text": "the message"} '
    "— pick funny, dramatic, or memorable ones]}. Never invent details or "
    "alter quotes."
)


def load_env_file(path: Path | None = None) -> None:
    path = path or Path(".env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_EMBED_CACHE = Path("data/embed_cache.sqlite")


def embed_parallel(texts: list[str], api_key: str, *, model: str, dims: int,
                   batch: int, workers: int = 4, unit: str = "texts"):
    """Embed texts with OpenAI, sending `workers` batches concurrently.

    Every finished batch is committed to data/embed_cache.sqlite, so a crash
    or Ctrl+C loses at most the in-flight batches and a rerun resumes.
    Returns an L2-normalized float32 array aligned with `texts`.
    """
    import hashlib
    import sqlite3

    import numpy as np

    def key(text: str) -> str:
        return hashlib.sha1(f"{model}|{dims}|{text}".encode()).hexdigest()

    _EMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = sqlite3.connect(_EMBED_CACHE)
    cache.execute("PRAGMA journal_mode=WAL")
    cache.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")

    keys = [key(t) for t in texts]
    out = np.empty((len(texts), dims), dtype=np.float32)
    wanted = set(keys)
    found = {k: v for k, v in cache.execute("SELECT k, v FROM emb")
             if k in wanted}
    for i, k in enumerate(keys):
        if k in found:
            out[i] = np.frombuffer(found[k], dtype=np.float32)

    todo = [i for i, k in enumerate(keys) if k not in found]
    print(f"  {len(texts) - len(todo):,} {unit} already cached, "
          f"{len(todo):,} to embed", flush=True)
    chunks = [todo[s:s + batch] for s in range(0, len(todo), batch)]

    def fetch(idx: list[int]) -> tuple[list[int], list]:
        payload = {"model": model, "input": [texts[i] for i in idx],
                   "dimensions": dims}
        for attempt in range(20):
            try:
                with httpx.Client(timeout=180) as client:
                    r = client.post("https://api.openai.com/v1/embeddings",
                                    json=payload,
                                    headers={"Authorization": f"Bearer {api_key}"})
                r.raise_for_status()
                return idx, r.json()["data"]
            except httpx.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and "insufficient_quota" in resp.text:
                    raise  # out of credits — retrying won't help
                if attempt == 19:
                    raise
                # Concurrent batches trip the tokens-per-minute limit; honor
                # Retry-After and jitter so workers don't retry in lockstep.
                hinted = resp.headers.get("retry-after") if resp is not None else None
                wait = float(hinted) if hinted else min(2 ** attempt, 60)
                wait += random.uniform(0, 1)
                code = resp.status_code if resp is not None else type(exc).__name__
                print(f"\n  retry {attempt + 1} after {code}, sleeping {wait:.0f}s",
                      flush=True)
                time.sleep(wait)
        raise AssertionError("unreachable")

    done = len(texts) - len(todo)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        for fut in as_completed([pool.submit(fetch, c) for c in chunks]):
            idx, data = fut.result()
            rows = []
            for item in data:
                i = idx[item["index"]]
                out[i] = item["embedding"]
                rows.append((keys[i], out[i].tobytes()))
            cache.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)", rows)
            cache.commit()
            done += len(data)
            print(f"\r  embedded {done:,}/{len(texts):,} {unit}", end="",
                  flush=True)
    finally:
        # On a fatal error, don't keep spending API calls on queued batches.
        pool.shutdown(wait=True, cancel_futures=True)
        cache.close()
    print(flush=True)
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.maximum(norms, 1e-9)


def _read_cache() -> dict:
    if _CACHE_PATH.exists():
        return json.loads(_CACHE_PATH.read_text())
    return {}


def _write_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1))


def _complete_json(cache_key: str, system_prompt: str, user_content: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "insert_openai_key_here":
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured — copy .env.example to .env "
                   "and add your key")

    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-5-nano"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=90,
        )
    except httpx.HTTPError as exc:
        logger.warning("OpenAI request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="could not reach OpenAI")
    if resp.status_code != 200:
        logger.warning("OpenAI returned %s for day-summary %s",
                       resp.status_code, cache_key)
        raise HTTPException(status_code=502,
                            detail=f"OpenAI error {resp.status_code}")
    return resp.json()["choices"][0]["message"]["content"]


def summarize_day(cache_key: str, person_name: str, day: str,
                  transcript: str) -> dict:
    cache = _read_cache()
    if cache_key in cache:
        return cache[cache_key]

    content = _complete_json(
        cache_key, _SYSTEM_PROMPT,
        f"Conversation between You and {person_name} on {day}:\n\n{transcript}")
    try:
        parsed = json.loads(content)
        result = {"summary": str(parsed.get("summary", content)),
                  "sentiment": parsed.get("sentiment")}
    except (json.JSONDecodeError, AttributeError):
        result = {"summary": content, "sentiment": None}

    cache[cache_key] = result
    _write_cache(cache)
    return result


def summarize_you_day(cache_key: str, day: str, transcript: str) -> dict:
    cache = _read_cache()
    if cache_key in cache:
        return cache[cache_key]

    content = _complete_json(
        cache_key, _YOU_DAY_PROMPT,
        f"Your messages across conversations on {day}:\n\n{transcript}")
    try:
        parsed = json.loads(content)
        quotes = [
            {"speaker": str(q.get("speaker", "")), "text": str(q.get("text", ""))}
            for q in parsed.get("quotes", []) if isinstance(q, dict)
        ]
        result = {"summary": str(parsed.get("summary", content)),
                  "sentiment": parsed.get("sentiment"),
                  "quotes": quotes}
    except (json.JSONDecodeError, AttributeError):
        result = {"summary": content, "sentiment": None, "quotes": []}

    cache[cache_key] = result
    _write_cache(cache)
    return result
