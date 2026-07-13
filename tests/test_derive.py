from datetime import datetime, timedelta, timezone

from ingest.derive import assign_sessions, compute_response_seconds, split_tapbacks

T0 = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def _row(chat_id, minutes, from_me):
    return {"chat_id": chat_id, "ts_utc": T0 + timedelta(minutes=minutes),
            "is_from_me": from_me}


def test_split_tapbacks():
    msgs = [
        {"msg_id": 1, "associated_message_type": 0, "item_type": 0},
        {"msg_id": 2, "associated_message_type": 2003, "item_type": 0,
         "associated_message_guid": "p:0/ABC-123"},
        {"msg_id": 3, "associated_message_type": 2000, "item_type": 0,
         "associated_message_guid": "bp:DEF-456"},
        {"msg_id": 4, "associated_message_type": 3003, "item_type": 0,
         "associated_message_guid": "p:0/ABC-123"},          # removal → dropped
        {"msg_id": 5, "associated_message_type": 0, "item_type": 2},  # group event → dropped
    ]
    real, tapbacks = split_tapbacks(msgs)
    assert [m["msg_id"] for m in real] == [1]
    assert [(t["kind"], t["target_guid"]) for t in tapbacks] == [
        ("laugh", "ABC-123"), ("love", "DEF-456")]


def test_sessions_split_on_gap():
    rows = [_row(1, 0, 0), _row(1, 10, 1), _row(1, 200, 0), _row(2, 5, 0)]
    assign_sessions(rows, gap_minutes=60)
    assert rows[0]["session_id"] == rows[1]["session_id"] == "1:0"
    assert rows[2]["session_id"] == "1:1"
    assert rows[3]["session_id"] == "2:0"


def test_response_seconds_direction_flip_only():
    rows = [_row(1, 0, 0), _row(1, 2, 1), _row(1, 3, 1), _row(1, 200, 0)]
    assign_sessions(rows)
    compute_response_seconds(rows, is_group={1: False})
    assert rows[0]["response_seconds"] is None          # first message
    assert rows[1]["response_seconds"] == 120.0         # flip: reply in 2 min
    assert rows[2]["response_seconds"] is None          # same sender again
    assert rows[3]["response_seconds"] is None          # new session


def test_response_seconds_skips_groups():
    rows = [_row(9, 0, 0), _row(9, 1, 1)]
    assign_sessions(rows)
    compute_response_seconds(rows, is_group={9: True})
    assert rows[1]["response_seconds"] is None
