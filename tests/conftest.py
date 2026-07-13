import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingest.chatdb import read_raw
from ingest.load import build_analytics_db
from server.app import create_app
from tests.fixtures import apple_ns, make_chat_db

# Deterministic ts_local regardless of machine timezone.
os.environ["TZ"] = "UTC"
time.tzset()


def _t(day, hour, minute):
    return apple_ns(datetime(2024, 6, day, hour, minute, tzinfo=timezone.utc))


@pytest.fixture(scope="session")
def analytics_db(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("api")
    chat = tmp / "chat.db"
    make_chat_db(
        chat,
        handles=[(1, "+15551234567", "iMessage"), (2, "+15559990000", "iMessage")],
        chats=[(1, None, 45), (2, "the squad", 43), (3, None, 45)],
        chat_handles=[(1, 1), (2, 1), (2, 2), (3, 2)],
        messages=[
            # 1:1 with Alice — Jun 1: her msg, my reply 2 min later; Jun 2: I initiate, she replies in 5 min
            {"msg_id": 1, "guid": "g1", "text": "hey 😂", "handle_id": 1,
             "chat_id": 1, "date": _t(1, 12, 0)},
            {"msg_id": 2, "guid": "g2", "text": "yo!", "handle_id": 0,
             "chat_id": 1, "date": _t(1, 12, 2), "is_from_me": 1},
            {"msg_id": 3, "guid": "g3", "text": "morning", "handle_id": 0,
             "chat_id": 1, "date": _t(2, 9, 0), "is_from_me": 1},
            {"msg_id": 4, "guid": "g4", "text": "hi", "handle_id": 1,
             "chat_id": 1, "date": _t(2, 9, 5)},
            # 1:1 with Bob — one incoming
            {"msg_id": 5, "guid": "g5", "text": "sup", "handle_id": 2,
             "chat_id": 3, "date": _t(1, 18, 0)},
            # group "the squad" — Alice, Bob, me, one message each
            {"msg_id": 6, "guid": "g6", "text": "group hi", "handle_id": 1,
             "chat_id": 2, "date": _t(1, 13, 0)},
            {"msg_id": 7, "guid": "g7", "text": "hello all", "handle_id": 2,
             "chat_id": 2, "date": _t(1, 13, 1)},
            {"msg_id": 8, "guid": "g8", "text": "sup squad", "handle_id": 0,
             "chat_id": 2, "date": _t(1, 13, 2), "is_from_me": 1},
            # tapbacks: Alice loves my g2; Bob laughs at my g8
            {"msg_id": 9, "guid": "g9", "handle_id": 1, "chat_id": 1,
             "date": _t(1, 12, 3), "associated_message_type": 2000,
             "associated_message_guid": "p:0/g2"},
            {"msg_id": 10, "guid": "g10", "handle_id": 2, "chat_id": 2,
             "date": _t(1, 13, 3), "associated_message_type": 2003,
             "associated_message_guid": "p:0/g8"},
        ],
    )
    out = tmp / "analytics.duckdb"
    build_analytics_db(out, read_raw(chat),
                       contacts={"5551234567": "Alice Smith",
                                 "5559990000": "Bob Jones"})
    return out


@pytest.fixture(scope="session")
def client(analytics_db):
    return TestClient(create_app(analytics_db))
