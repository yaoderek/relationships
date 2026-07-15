"""Synthetic demo analytics.duckdb — develop the dashboard without Full Disk Access."""
import argparse
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.chatdb import read_raw
from ingest.handles import normalize_handle
from ingest.load import build_analytics_db
from tests.fixtures import apple_ns, make_chat_db

PEOPLE = [(1, "+15551230001", "Alice Demo"), (2, "+15551230002", "Bob Demo"),
          (3, "+15551230003", "Carol Demo")]
PHRASES = ["hey", "lol 😂", "sounds good", "omw", "nice 🎉", "ok ok",
           "what do you think?", "haha yes", "brutal 💀", "coffee?"]


def main() -> None:
    p = argparse.ArgumentParser(prog="python scripts/make_demo.py")
    p.add_argument("--out", type=Path, default=Path("data/analytics.duckdb"))
    args = p.parse_args()

    rng = random.Random(42)
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    chat_path = data_dir / "demo_chat.db"
    chat_path.unlink(missing_ok=True)

    handles = [(hid, num, "iMessage") for hid, num, _ in PEOPLE]
    chats = [(1, None, 45), (2, None, 45), (3, None, 45), (4, "the squad", 43)]
    chat_handles = [(1, 1), (2, 2), (3, 3), (4, 1), (4, 2), (4, 3)]

    messages, msg_id = [], 1
    start = datetime(2023, 1, 1, 9, 0, tzinfo=timezone.utc)
    for day in range(540):
        for chat_id, members, base in ((1, [1], 6), (2, [2], 3), (3, [3], 1), (4, [1, 2, 3], 4)):
            wave = max(0.0, 1 + 0.9 * math.sin(day / 60 + chat_id * 2))
            n = max(0, int(rng.gauss(base * wave, 1.5)))
            minute = 0
            for i in range(n):
                minute += rng.randint(1, 120)
                ts = start + timedelta(days=day, minutes=minute)
                from_me = (i % 2 == 0) if chat_id != 4 else rng.random() < 0.3
                messages.append({
                    "msg_id": msg_id, "guid": f"g{msg_id}",
                    "text": rng.choice(PHRASES),
                    "handle_id": 0 if from_me else rng.choice(members),
                    "chat_id": chat_id, "date": apple_ns(ts),
                    "is_from_me": int(from_me),
                })
                msg_id += 1

    make_chat_db(chat_path, handles, chats, chat_handles, messages)
    contacts = {normalize_handle(num): name for _, num, name in PEOPLE}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build_analytics_db(args.out, read_raw(chat_path), contacts)
    print(f"Wrote {args.out} with {msg_id - 1} messages")


if __name__ == "__main__":
    main()
