from ingest.textstats import list_emojis, text_stats


def test_plain_text():
    assert text_stats("hello there world") == (17, 3, 0)


def test_emoji_counted():
    chars, words, emojis = text_stats("lol 😂😂 nice 🎉")
    assert emojis == 3
    assert words == 4


def test_none_and_empty():
    assert text_stats(None) == (0, 0, 0)
    assert text_stats("") == (0, 0, 0)


def test_list_emojis_keeps_duplicates():
    assert list_emojis("😂 ok 😂🎉") == ["😂", "😂", "🎉"]
    assert list_emojis(None) == []
