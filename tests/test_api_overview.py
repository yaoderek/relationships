def test_overview_daily(client):
    series = client.get("/api/overview/timeseries?bucket=day").json()
    assert series == [
        {"bucket": "2024-06-01", "sent": 2, "received": 4},
        {"bucket": "2024-06-02", "sent": 1, "received": 1},
    ]


def test_invalid_bucket_rejected(client):
    assert client.get("/api/overview/timeseries?bucket=year; DROP").status_code == 422
