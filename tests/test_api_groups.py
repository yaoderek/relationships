import pytest


def _squad_id(client):
    return client.get("/api/groups").json()[0]["chat_id"]


def test_group_leaderboard(client):
    groups = client.get("/api/groups").json()
    assert len(groups) == 1
    g = groups[0]
    assert g["name"] == "the squad"
    assert g["participants"] == 2
    assert g["total"] == 3
    assert g["my_share"] == pytest.approx(1 / 3)


def test_group_timeseries(client):
    gid = _squad_id(client)
    series = client.get(f"/api/groups/{gid}/timeseries?bucket=day").json()
    assert series == [{"bucket": "2024-06-01", "total": 3, "mine": 1}]


def test_group_heatmap(client):
    gid = _squad_id(client)
    cells = client.get(f"/api/groups/{gid}/heatmap").json()
    assert cells == [{"weekday": 6, "hour": 13, "count": 3}]


def test_group_stats(client):
    gid = _squad_id(client)
    s = client.get(f"/api/groups/{gid}/stats").json()
    assert s["name"] == "the squad"
    assert s["my_share"] == pytest.approx(1 / 3)
    assert s["session_count"] == 1
    assert s["busiest_day"] == {"date": "2024-06-01", "count": 3}
    by_name = {m["display_name"]: m for m in s["members"]}
    assert set(by_name) == {"Alice Smith", "Bob Jones", "You"}
    assert by_name["You"]["person_id"] is None
    assert by_name["You"]["count"] == 1
    assert by_name["You"]["share"] == pytest.approx(1 / 3)
    assert by_name["You"]["tapbacks_received"] == 1      # Bob laughed at g8
    assert by_name["Alice Smith"]["tapbacks_received"] == 0


def test_group_stats_404s(client):
    assert client.get("/api/groups/1/stats").status_code == 404      # 1:1 chat
    assert client.get("/api/groups/99999/stats").status_code == 404  # unknown


def _alice_id(client):
    return next(p["person_id"] for p in client.get("/api/persons").json()
                if p["display_name"] == "Alice Smith")


def _bob_id(client):
    return next(p["person_id"] for p in client.get("/api/persons").json()
                if p["display_name"] == "Bob Jones")


def test_group_member_stats_alice(client):
    gid = _squad_id(client)
    s = client.get(f"/api/groups/{gid}/members/{_alice_id(client)}/stats").json()
    assert s["display_name"] == "Alice Smith"
    assert s["count"] == 1
    assert s["share"] == pytest.approx(1 / 3)
    assert s["sessions_total"] == 1
    assert s["sessions_participated"] == 1
    assert s["sessions_ghosted"] == 0
    assert s["sessions_ended"] == 0            # my msg was last in the session
    assert s["top_words"] == [{"word": "group", "count": 1}]  # "hi" too short
    assert s["top_reactions_given"] == []      # her tapback was in the 1:1 chat
    assert s["tapbacks_received"] == 0


def test_group_member_stats_me(client):
    gid = _squad_id(client)
    s = client.get(f"/api/groups/{gid}/members/0/stats").json()
    assert s["display_name"] == "You"
    assert s["count"] == 1
    assert s["sessions_ended"] == 1            # "sup squad" ended the session
    assert s["tapbacks_received"] == 1         # Bob laughed at g8
    assert {"word": "sup", "count": 1} in s["top_words"]


def test_group_member_reactions_given(client):
    gid = _squad_id(client)
    s = client.get(f"/api/groups/{gid}/members/{_bob_id(client)}/stats").json()
    assert s["top_reactions_given"] == [{"kind": "laugh", "count": 1}]


def test_group_member_timeseries(client):
    gid = _squad_id(client)
    series = client.get(
        f"/api/groups/{gid}/members/{_alice_id(client)}/timeseries?bucket=day").json()
    assert series == [{"bucket": "2024-06-01", "count": 1}]


def test_group_member_404s(client):
    gid = _squad_id(client)
    assert client.get(f"/api/groups/{gid}/members/9999/stats").status_code == 404
    assert client.get("/api/groups/1/members/0/stats").status_code == 404  # 1:1 chat
