from ingest.typedstream import decode_attributed_body

MARKER = b"\x01\x94\x84\x01\x2b"


def _blob(text: bytes, length_bytes: bytes) -> bytes:
    return b"\x04\x0bstreamtyped\x81junkNSString" + MARKER + length_bytes + text + b"\x86trailer"


def test_short_string():
    assert decode_attributed_body(_blob(b"hello", bytes([5]))) == "hello"


def test_two_byte_length():
    text = b"x" * 300
    blob = _blob(text, b"\x81" + (300).to_bytes(2, "little"))
    assert decode_attributed_body(blob) == "x" * 300


def test_four_byte_length():
    text = b"y" * 70000
    blob = _blob(text, b"\x82" + (70000).to_bytes(4, "little"))
    assert decode_attributed_body(blob) == "y" * 70000


def test_unicode_text():
    text = "héllo 🎉".encode()
    assert decode_attributed_body(_blob(text, bytes([len(text)]))) == "héllo 🎉"


def test_garbage_and_empty_return_none():
    assert decode_attributed_body(None) is None
    assert decode_attributed_body(b"") is None
    assert decode_attributed_body(b"no marker here") is None


def test_truncated_after_two_byte_length_marker_returns_none():
    # Blob ends immediately after the \x81 marker byte — no length bytes follow.
    blob = b"\x04\x0bstreamtyped\x81junkNSString" + MARKER + b"\x81"
    assert decode_attributed_body(blob) is None


def test_partial_length_bytes_return_none():
    # \x81 with only 1 of 2 length bytes present.
    blob = b"\x04\x0bstreamtyped\x81junkNSString" + MARKER + b"\x81\x2c"
    assert decode_attributed_body(blob) is None
    # \x82 with only 3 of 4 length bytes present.
    blob = b"\x04\x0bstreamtyped\x81junkNSString" + MARKER + b"\x82\x01\x02\x03"
    assert decode_attributed_body(blob) is None


def test_declared_length_exceeds_payload_returns_none():
    # Length byte says 50 but only 13 bytes (5 payload + 8 trailer) remain.
    assert decode_attributed_body(_blob(b"hello", bytes([50]))) is None
