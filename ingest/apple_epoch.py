from datetime import datetime, timedelta, timezone

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# Values above this are nanoseconds; below, legacy whole seconds.
_NS_THRESHOLD = 10**12


def apple_to_utc(raw: int | None) -> datetime | None:
    if not raw:
        return None
    seconds = raw / 1e9 if raw > _NS_THRESHOLD else float(raw)
    return APPLE_EPOCH + timedelta(seconds=seconds)
