import json
import logging
import os
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
