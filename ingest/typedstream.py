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
        length = int.from_bytes(blob[pos + 1 : pos + 3], "little")
        pos += 3
    elif marker == 0x82:
        length = int.from_bytes(blob[pos + 1 : pos + 5], "little")
        pos += 5
    else:
        length = marker
        pos += 1
    return blob[pos : pos + length].decode("utf-8", errors="replace")
