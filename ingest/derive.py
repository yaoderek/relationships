from collections import defaultdict

TAPBACK_KINDS = {2000: "love", 2001: "like", 2002: "dislike",
                 2003: "laugh", 2004: "emphasize", 2005: "question"}


def _strip_target_guid(guid: str | None) -> str:
    if not guid:
        return ""
    if "/" in guid:
        return guid.split("/", 1)[1]
    return guid.removeprefix("bp:")


def split_tapbacks(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    real, tapbacks = [], []
    for m in messages:
        assoc = m.get("associated_message_type") or 0
        if assoc in TAPBACK_KINDS:
            tapbacks.append({**m, "kind": TAPBACK_KINDS[assoc],
                             "target_guid": _strip_target_guid(m.get("associated_message_guid"))})
        elif assoc == 0 and (m.get("item_type") or 0) == 0:
            real.append(m)
        # anything else (tapback removals, system/group events) is dropped
    return real, tapbacks


def assign_sessions(rows: list[dict], gap_minutes: int = 60) -> None:
    by_chat = defaultdict(list)
    for r in rows:
        by_chat[r["chat_id"]].append(r)
    for chat_id, chat_rows in by_chat.items():
        chat_rows.sort(key=lambda r: r["ts_utc"])
        session = 0
        prev_ts = None
        for r in chat_rows:
            if prev_ts is not None and (r["ts_utc"] - prev_ts).total_seconds() > gap_minutes * 60:
                session += 1
            r["session_id"] = f"{chat_id}:{session}"
            prev_ts = r["ts_utc"]


def compute_response_seconds(rows: list[dict], is_group: dict[int, bool]) -> None:
    by_chat = defaultdict(list)
    for r in rows:
        r.setdefault("response_seconds", None)
        by_chat[r["chat_id"]].append(r)
    for chat_id, chat_rows in by_chat.items():
        if is_group.get(chat_id):
            continue
        chat_rows.sort(key=lambda r: r["ts_utc"])
        for prev, cur in zip(chat_rows, chat_rows[1:]):
            if (cur["session_id"] == prev["session_id"]
                    and bool(cur["is_from_me"]) != bool(prev["is_from_me"])):
                cur["response_seconds"] = (cur["ts_utc"] - prev["ts_utc"]).total_seconds()
