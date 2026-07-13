from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from ingest.chatdb import read_raw
from ingest.load import build_analytics_db
from server.app import create_app
from tests.fixtures import apple_ns, make_chat_db


def _t(day, hour, minute):
    return apple_ns(datetime(2024, 6, day, hour, minute, tzinfo=timezone.utc))


@pytest.fixture(scope="module")
def games_client(tmp_path_factory) -> TestClient:
    """Richer fixture than conftest's: 4 friends, long sessions, repeated words."""
    tmp = tmp_path_factory.mktemp("games")
    chat = tmp / "chat.db"
    msgs = [
        # Alice 1:1 (chat 1) — one 7-message session on Jun 1.
        # m6 is the only finish-the-convo candidate in the whole fixture:
        # >= 4 prior messages in session, previous message from friend, len >= 8.
        {"msg_id": 1, "guid": "g1", "text": "are we still on for tonight",
         "handle_id": 1, "chat_id": 1, "date": _t(1, 12, 0)},
        {"msg_id": 2, "guid": "g2", "text": "yeah leaving at seven",
         "handle_id": 0, "chat_id": 1, "date": _t(1, 12, 1), "is_from_me": 1},
        {"msg_id": 3, "guid": "g3", "text": "cool should i bring anything",
         "handle_id": 1, "chat_id": 1, "date": _t(1, 12, 2)},
        {"msg_id": 4, "guid": "g4", "text": "maybe just yourself haha",
         "handle_id": 0, "chat_id": 1, "date": _t(1, 12, 3), "is_from_me": 1},
        {"msg_id": 5, "guid": "g5", "text": "bet see you soon",
         "handle_id": 1, "chat_id": 1, "date": _t(1, 12, 4)},
        {"msg_id": 6, "guid": "g6", "text": "sounds good see you there",
         "handle_id": 0, "chat_id": 1, "date": _t(1, 12, 5), "is_from_me": 1},
        {"msg_id": 7, "guid": "g7", "text": "here now come outside",
         "handle_id": 1, "chat_id": 1, "date": _t(1, 12, 6)},
        # Bob 1:1 (chat 2) — two short sessions; Bob says "bruh" in all 4 msgs.
        {"msg_id": 8, "guid": "g8", "text": "bruh that game was crazy",
         "handle_id": 2, "chat_id": 2, "date": _t(2, 10, 0)},
        {"msg_id": 9, "guid": "g9", "text": "omw give me ten minutes",
         "handle_id": 0, "chat_id": 2, "date": _t(2, 10, 1), "is_from_me": 1},
        {"msg_id": 10, "guid": "g10", "text": "bruh hurry up man",
         "handle_id": 2, "chat_id": 2, "date": _t(2, 10, 2)},
        {"msg_id": 11, "guid": "g11", "text": "bruh you seeing this",
         "handle_id": 2, "chat_id": 2, "date": _t(2, 14, 0)},
        {"msg_id": 12, "guid": "g12", "text": "haha that was so funny dude",
         "handle_id": 0, "chat_id": 2, "date": _t(2, 14, 1), "is_from_me": 1},
        {"msg_id": 13, "guid": "g13", "text": "bruh unreal",
         "handle_id": 2, "chat_id": 2, "date": _t(2, 14, 2)},
        # Cara 1:1 (chat 3) — short session; my reply feeds the distractor pool.
        {"msg_id": 20, "guid": "g20", "text": "did you finish the project",
         "handle_id": 3, "chat_id": 3, "date": _t(4, 20, 0)},
        {"msg_id": 21, "guid": "g21", "text": "nah i cant make it tonight",
         "handle_id": 0, "chat_id": 3, "date": _t(4, 20, 1), "is_from_me": 1},
        {"msg_id": 22, "guid": "g22", "text": "lol classic",
         "handle_id": 3, "chat_id": 3, "date": _t(4, 20, 2)},
        # Dan 1:1 (chat 4) — Dan says "bruh" in 3 of 5 msgs (lower rate than Bob).
        {"msg_id": 14, "guid": "g14", "text": "bruh i overslept again",
         "handle_id": 4, "chat_id": 4, "date": _t(3, 9, 0)},
        {"msg_id": 15, "guid": "g15", "text": "lets grab food tomorrow",
         "handle_id": 0, "chat_id": 4, "date": _t(3, 9, 1), "is_from_me": 1},
        {"msg_id": 16, "guid": "g16", "text": "bruh maybe",
         "handle_id": 4, "chat_id": 4, "date": _t(3, 9, 2)},
        {"msg_id": 17, "guid": "g17", "text": "bruh actually yes",
         "handle_id": 4, "chat_id": 4, "date": _t(3, 9, 3)},
        {"msg_id": 18, "guid": "g18", "text": "what time works",
         "handle_id": 4, "chat_id": 4, "date": _t(3, 9, 4)},
        {"msg_id": 19, "guid": "g19", "text": "let me check and text back",
         "handle_id": 4, "chat_id": 4, "date": _t(3, 9, 5)},
    ]
    make_chat_db(
        chat,
        handles=[(1, "+15551230001", "iMessage"), (2, "+15551230002", "iMessage"),
                 (3, "+15551230003", "iMessage"), (4, "+15551230004", "iMessage")],
        chats=[(1, None, 45), (2, None, 45), (3, None, 45), (4, None, 45)],
        chat_handles=[(1, 1), (2, 2), (3, 3), (4, 4)],
        messages=msgs,
    )
    out = tmp / "analytics.duckdb"
    build_analytics_db(out, read_raw(chat),
                       contacts={"5551230001": "Alice", "5551230002": "Bob",
                                 "5551230003": "Cara", "5551230004": "Dan"})
    return TestClient(create_app(out))


def test_who_said_it_round(games_client):
    r = games_client.get("/api/games/who-said-it")
    assert r.status_code == 200
    round_ = r.json()
    msgs = round_["messages"]
    assert 3 <= len(msgs) <= 5
    assert sum(not m["is_from_me"] for m in msgs) >= 2
    assert all(set(m) == {"text", "is_from_me"} for m in msgs)
    choices = round_["choices"]
    assert len(choices) == 4
    assert len({c["person_id"] for c in choices}) == 4
    assert round_["answer_person_id"] in {c["person_id"] for c in choices}
    assert round_["date"].startswith("2024-06-")


def test_who_said_it_404_when_too_few_contacts(client):
    # conftest fixture has only 2 contacts (< 4 needed for choices)
    r = client.get("/api/games/who-said-it")
    assert r.status_code == 404
