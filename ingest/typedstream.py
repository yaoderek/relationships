_PREFIX = b"NSString"
_MARKER_LEN = 5  # \x01\x94\x84\x01\x2b after the class name


def decode_attributed_body(blob: bytes | None) -> str | None:
    if not blob:
        return None
    idx = blob.find(_PREFIX)
    if idx == -1:
        return None
    pos = idx + len(_PREFIX) + _MARKER_LEN
    if pos >= len(blob):
        return None
    marker = blob[pos]
    if marker == 0x81:
        raw = blob[pos + 1 : pos + 3]
        if len(raw) < 2:
            return None
        length = int.from_bytes(raw, "little")
        pos += 3
    elif marker == 0x82:
        raw = blob[pos + 1 : pos + 5]
        if len(raw) < 4:
            return None
        length = int.from_bytes(raw, "little")
        pos += 5
    else:
        length = marker
        pos += 1
    chunk = blob[pos : pos + length]
    if len(chunk) < length:
        return None
    return chunk.decode("utf-8", errors="replace")
