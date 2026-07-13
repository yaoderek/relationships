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
