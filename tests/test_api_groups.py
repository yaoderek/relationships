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
    assert set(by_name) == {"Alice Smith", "Bob Jones", "Me"}
    assert by_name["Me"]["person_id"] is None
    assert by_name["Me"]["count"] == 1
    assert by_name["Me"]["share"] == pytest.approx(1 / 3)
    assert by_name["Me"]["tapbacks_received"] == 1      # Bob laughed at g8
    assert by_name["Alice Smith"]["tapbacks_received"] == 0


def test_group_stats_404s(client):
    assert client.get("/api/groups/1/stats").status_code == 404      # 1:1 chat
    assert client.get("/api/groups/99999/stats").status_code == 404  # unknown
