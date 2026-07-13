from ingest.phrases import log_odds, ngram_counts, tokenize


def test_tokenize_normalizes_curly_apostrophes():
    assert tokenize("Don’t WORRY bro") == ["don't", "worry", "bro"]


def test_ngram_counts_sizes():
    c = ngram_counts(["hi there friend"], sizes=(1, 2))
    assert c["hi"] == 1
    assert c["hi there"] == 1
    assert c["there friend"] == 1
    assert "hi there friend" not in c


def test_ngram_counts_accumulates_repeats():
    c = ngram_counts(["womp womp", "womp womp"], sizes=(2,))
    assert c["womp womp"] == 2


def test_log_odds_ranks_distinctive_phrases_first():
    target = ngram_counts(["womp womp"] * 10 + ["sounds good"] * 10, sizes=(2,))
    background = ngram_counts(["sounds good"] * 200, sizes=(2,))
    ranked = log_odds(target, background, min_count=1)
    assert ranked[0][0] == "womp womp"          # unique to target
    assert ranked[0][2] > 0
    scores = {phrase: z for phrase, _, z in ranked}
    assert scores["womp womp"] > scores["sounds good"]


def test_log_odds_min_count_filters():
    target = ngram_counts(["rare gem"], sizes=(2,))
    assert log_odds(target, ngram_counts([], sizes=(2,)), min_count=2) == []
