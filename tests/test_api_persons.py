def test_persons_leaderboard(client):
    people = client.get("/api/persons").json()
    assert [p["display_name"] for p in people] == ["Alice Smith", "Bob Jones"]
    alice, bob = people
    assert (alice["total"], alice["sent"], alice["received"]) == (4, 2, 2)
    assert (bob["total"], bob["sent"], bob["received"]) == (1, 0, 1)
    assert alice["first_ts"].startswith("2024-06-01")
    assert alice["last_ts"].startswith("2024-06-02")


def _alice_id(client):
    return next(p["person_id"] for p in client.get("/api/persons").json()
                if p["display_name"] == "Alice Smith")


def test_person_timeseries_daily(client):
    pid = _alice_id(client)
    series = client.get(f"/api/persons/{pid}/timeseries?bucket=day").json()
    assert series == [
        {"bucket": "2024-06-01", "sent": 1, "received": 1},
        {"bucket": "2024-06-02", "sent": 1, "received": 1},
    ]


def test_person_timeseries_include_groups(client):
    pid = _alice_id(client)
    series = client.get(
        f"/api/persons/{pid}/timeseries?bucket=day&include_groups=true").json()
    assert series[0] == {"bucket": "2024-06-01", "sent": 1, "received": 2}


def test_person_stats(client):
    pid = _alice_id(client)
    s = client.get(f"/api/persons/{pid}/stats").json()
    assert s["display_name"] == "Alice Smith"
    assert s["median_response_seconds_me"] == 120.0
    assert s["median_response_seconds_them"] == 300.0
    assert s["initiation_rate_me"] == 0.5
    assert s["top_emojis_them"] == [{"emoji": "😂", "count": 1}]
    assert s["top_emojis_me"] == []
    assert s["tapbacks_from_them"] == [{"kind": "love", "count": 1}]
    assert s["tapbacks_from_me"] == []


def test_person_conversation_stats(client):
    pid = _alice_id(client)
    s = client.get(f"/api/persons/{pid}/stats").json()
    # every reply in the fixture is a single message
    assert s["avg_reply_block_me"] == 1.0
    assert s["avg_reply_block_them"] == 1.0
    assert s["reply_block_ratio"] == 1.0
    assert s["double_texts_me"] == 1       # "morning" sent after unanswered "yo!"
    assert s["double_texts_them"] == 0
    assert s["ghosts_by_them"] == 1        # Jun 1 session ended on my message
    assert s["ghosts_by_me"] == 1          # Jun 2 session ended on hers
    assert s["avg_session_seconds"] == 210.0   # (120 + 300) / 2
    assert s["avg_session_messages"] == 2.0


def test_person_stats_404(client):
    assert client.get("/api/persons/9999/stats").status_code == 404


def test_person_heatmap(client):
    pid = _alice_id(client)
    cells = client.get(f"/api/persons/{pid}/heatmap").json()
    assert {"weekday": 6, "hour": 12, "count": 2} in cells   # Sat Jun 1
    assert {"weekday": 0, "hour": 9, "count": 2} in cells    # Sun Jun 2


def test_compare(client):
    people = client.get("/api/persons").json()
    ids = ",".join(str(p["person_id"]) for p in people)
    out = client.get(f"/api/compare?ids={ids}&bucket=month").json()
    totals = {o["display_name"]: o["series"][0]["total"] for o in out}
    assert totals == {"Alice Smith": 4, "Bob Jones": 1}
