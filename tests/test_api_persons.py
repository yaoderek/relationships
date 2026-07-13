def test_persons_leaderboard(client):
    people = client.get("/api/persons").json()
    assert [p["display_name"] for p in people] == ["Alice Smith", "Bob Jones"]
    alice, bob = people
    assert (alice["total"], alice["sent"], alice["received"]) == (4, 2, 2)
    assert (bob["total"], bob["sent"], bob["received"]) == (1, 0, 1)
    assert alice["first_ts"].startswith("2024-06-01")
    assert alice["last_ts"].startswith("2024-06-02")
