def test_you_stats(client):
    s = client.get("/api/you").json()
    assert s["sent_total"] == 3                       # yo!, morning, sup squad
    assert s["busiest_day"] == {"date": "2024-06-01", "count": 2}
    words = {w["word"] for w in s["top_words"]}
    assert {"morning", "sup", "squad"} <= words
    assert s["top_sentences"] == []                   # nothing repeated 3+ times
    assert s["top_emojis"] == []                      # no emoji in my texts
    assert s["reactions_given"] == []                 # no tapbacks from me
    assert s["double_texts"] == 1                     # "morning" after unanswered "yo!"
    assert s["avg_texts_per_reply"] == 1.0
    assert {"weekday": 6, "hour": 12, "count": 1} in s["heatmap"]


def test_persons_have_streaks(client):
    people = client.get("/api/persons").json()
    alice = next(p for p in people if p["display_name"] == "Alice Smith")
    assert alice["streak_days"] == 0    # fixture data is from 2024, no live streak
