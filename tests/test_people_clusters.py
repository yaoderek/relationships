import numpy as np

from scripts.language import pick_kmeans


def _unit(rows):
    x = np.asarray(rows, dtype=np.float32)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def test_pick_kmeans_finds_two_obvious_blobs():
    rng = np.random.default_rng(0)
    blob_a = rng.normal([10, 0, 0], 0.1, (12, 3))
    blob_b = rng.normal([0, 10, 0], 0.1, (12, 3))
    x = _unit(np.vstack([blob_a, blob_b]))
    assign, centroids, k = pick_kmeans(x, k_range=range(2, 6))
    assert k == 2
    assert len(set(assign[:12].tolist())) == 1     # blob A in one cluster
    assert len(set(assign[12:].tolist())) == 1     # blob B in another
    assert assign[0] != assign[12]


def test_pick_kmeans_three_blobs():
    rng = np.random.default_rng(1)
    blobs = [rng.normal(center, 0.05, (10, 3))
             for center in ([10, 0, 0], [0, 10, 0], [0, 0, 10])]
    x = _unit(np.vstack(blobs))
    _assign, _c, k = pick_kmeans(x, k_range=range(2, 6))
    assert k == 3
