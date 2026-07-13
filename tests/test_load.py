from datetime import datetime, timezone

import duckdb

from ingest.chatdb import read_raw
from ingest.load import build_analytics_db, resolve_persons
from tests.fixtures import apple_ns, make_chat_db

T = lambda h, m: datetime(2024, 6, 1, h, m, tzinfo=timezone.utc)


def test_resolve_persons_merges_contact_handles():
    handles = [{"handle_id": 1, "id": "+15551234567", "service": "iMessage"},
               {"handle_id": 2, "id": "alice@example.com", "service": "iMessage"},
               {"handle_id": 3, "id": "+15559990000", "service": "SMS"}]
    contacts = {"5551234567": "Alice Smith", "alice@example.com": "Alice Smith"}
    persons, handle_person = resolve_persons(handles, contacts, None)
    assert handle_person[1] == handle_person[2] != handle_person[3]
    by_id = {p["person_id"]: p for p in persons}
    assert by_id[handle_person[1]]["display_name"] == "Alice Smith"
    assert by_id[handle_person[3]] == {"person_id": handle_person[3],
                                       "display_name": "+15559990000",
                                       "source": "unmatched"}


def test_resolve_persons_overrides():
    handles = [{"handle_id": 1, "id": "+15551111111", "service": "SMS"},
               {"handle_id": 2, "id": "+15552222222", "service": "SMS"}]
    overrides = {"merge": [{"name": "Gym Buddy",
                            "handles": ["+15551111111", "+15552222222"]}],
                 "rename": {}}
    persons, handle_person = resolve_persons(handles, {}, overrides)
    assert handle_person[1] == handle_person[2]
    assert persons[0]["display_name"] == "Gym Buddy"
    assert persons[0]["source"] == "override"


def _build_chat_db(tmp_path):
    db = tmp_path / "chat.db"
    make_chat_db(
        db,
        handles=[(1, "+15551234567", "iMessage"), (2, "+15559990000", "iMessage")],
        chats=[(1, None, 45), (2, "the squad", 43)],
        chat_handles=[(1, 1), (2, 1), (2, 2)],
        messages=[
            # 1:1 with Alice: her msg, then my reply 2 min later with an emoji
            {"msg_id": 1, "guid": "g1", "text": "hey 😂", "handle_id": 1,
             "chat_id": 1, "date": apple_ns(T(12, 0))},
            {"msg_id": 2, "guid": "g2", "text": "yo!", "handle_id": 0,
             "chat_id": 1, "date": apple_ns(T(12, 2)), "is_from_me": 1},
            # her tapback on my reply
            {"msg_id": 3, "guid": "g3", "handle_id": 1, "chat_id": 1,
             "date": apple_ns(T(12, 3)), "associated_message_type": 2000,
             "associated_message_guid": "p:0/g2"},
            # group chat: one from Bob, one from me
            {"msg_id": 4, "guid": "g4", "text": "group hi", "handle_id": 2,
             "chat_id": 2, "date": apple_ns(T(13, 0))},
            {"msg_id": 5, "guid": "g5", "text": "sup", "handle_id": 0,
             "chat_id": 2, "date": apple_ns(T(13, 1)), "is_from_me": 1},
        ],
        attachments=[(2, "image/png", 999)],
    )
    return db


def test_build_analytics_db(tmp_path):
    raw = read_raw(_build_chat_db(tmp_path))
    out = tmp_path / "analytics.duckdb"
    build_analytics_db(out, raw, contacts={"5551234567": "Alice Smith"})
    con = duckdb.connect(str(out), read_only=True)

    assert con.execute("SELECT count(*) FROM persons").fetchone()[0] == 2
    assert con.execute(
        "SELECT is_group FROM chats ORDER BY chat_id").fetchall() == [(False,), (True,)]
    assert con.execute("SELECT count(*) FROM messages").fetchone()[0] == 4  # tapback excluded

    # my 1:1 reply is attributed to Alice and has a 120s response time
    pid_alice = con.execute(
        "SELECT person_id FROM persons WHERE display_name='Alice Smith'").fetchone()[0]
    row = con.execute(
        "SELECT person_id, response_seconds, has_attachment FROM messages WHERE guid='g2'"
    ).fetchone()
    assert row == (pid_alice, 120.0, True)

    # my group message has no person attribution
    assert con.execute(
        "SELECT person_id FROM messages WHERE guid='g5'").fetchone() == (None,)

    assert con.execute(
        "SELECT kind, is_from_me FROM tapbacks").fetchall() == [("love", False)]
    assert con.execute(
        "SELECT emoji FROM emoji_uses").fetchall() == [("😂",)]
    assert con.execute(
        "SELECT participant_count FROM chats WHERE chat_id=2").fetchone() == (2,)
    con.close()
