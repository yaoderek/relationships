"""Distinctive-phrase scoring: n-gram counting + log-odds with a Dirichlet prior.

The scoring follows Monroe et al. (2008), "Fightin' Words": phrases are ranked
by the z-score of the log-odds ratio between a target corpus and a background
corpus, with the combined corpus acting as the prior. High scores mean "said
far more often in the target corpus than the background would predict".
"""
import math
import re
from collections import Counter

_WORD_RE = re.compile(r"[a-z']+")


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower().replace("\u2019", "'"))


def ngram_counts(texts: list[str], sizes: tuple[int, ...] = (2, 3)) -> Counter:
    counts: Counter = Counter()
    for text in texts:
        words = tokenize(text)
        for n in sizes:
            for i in range(len(words) - n + 1):
                counts[" ".join(words[i:i + n])] += 1
    return counts


def log_odds(target: Counter, background: Counter,
             min_count: int = 5, prior_scale: float = 10.0,
             limit: int = 50) -> list[tuple[str, int, float]]:
    """Return [(phrase, target_count, z_score)] sorted by z descending."""
    n_target = sum(target.values())
    n_background = sum(background.values())
    combined = target + background
    n_combined = sum(combined.values())
    if n_target == 0 or n_combined == 0:
        return []

    scored = []
    for phrase, y in target.items():
        if y < min_count:
            continue
        x = background.get(phrase, 0)
        a = prior_scale * combined[phrase] / n_combined
        a0 = prior_scale
        delta = (math.log((y + a) / (n_target + a0 - y - a))
                 - math.log((x + a) / (n_background + a0 - x - a)))
        var = 1.0 / (y + a) + 1.0 / (x + a)
        scored.append((phrase, y, delta / math.sqrt(var)))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:limit]
