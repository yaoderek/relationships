from datetime import datetime, timezone

from ingest.apple_epoch import APPLE_EPOCH, apple_to_utc


def test_nanosecond_value():
    # 2023-03-15 12:00:00 UTC = unix 1678881600; minus unix(2001-01-01)=978307200
    # → 700,574,400 s after the Apple epoch
    raw = 700_574_400 * 10**9
    assert apple_to_utc(raw) == datetime(2023, 3, 15, 12, 0, tzinfo=timezone.utc)


def test_legacy_seconds_value():
    # pre-High Sierra rows store plain seconds
    raw = 700_574_400
    assert apple_to_utc(raw) == datetime(2023, 3, 15, 12, 0, tzinfo=timezone.utc)


def test_zero_and_none_are_none():
    assert apple_to_utc(0) is None
    assert apple_to_utc(None) is None


def test_epoch_constant():
    assert APPLE_EPOCH == datetime(2001, 1, 1, tzinfo=timezone.utc)
