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


def test_you_word_context(client):
    out = client.get("/api/you/word-context?word=sup").json()
    assert out == [{"text": "sup squad", "count": 1}]
    assert client.get("/api/you/word-context?word=zzz").json() == []


def test_you_vernacular_timeline(client):
    out = client.get("/api/you/vernacular-timeline").json()
    assert len(out) == 1
    assert out[0]["bucket"] == "2024"
    words = {w["word"] for w in out[0]["words"]}
    assert {"morning", "sup", "squad"} <= words


def test_you_hot_days(client):
    days = client.get("/api/you/hot-days").json()
    assert days[0]["date"] == "2024-06-01"
    assert days[0]["count"] == 6
    assert days[0]["sent"] == 2
    assert days[0]["top_contact"] == "Alice Smith"
    assert days[1] == {"date": "2024-06-02", "count": 2, "sent": 1,
                       "top_contact": "Alice Smith"}


def test_persons_have_streaks(client):
    people = client.get("/api/persons").json()
    alice = next(p for p in people if p["display_name"] == "Alice Smith")
    assert alice["streak_days"] == 0    # fixture data is from 2024, no live streak
