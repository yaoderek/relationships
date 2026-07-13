from ingest.handles import normalize_handle


def test_email_lowercased():
    assert normalize_handle(" Alice@Example.COM ") == "alice@example.com"


def test_us_phone_variants_collapse():
    assert normalize_handle("+1 (555) 123-4567") == "5551234567"
    assert normalize_handle("15551234567") == "5551234567"
    assert normalize_handle("555-123-4567") == "5551234567"


def test_international_number_keeps_digits():
    assert normalize_handle("+44 20 7946 0958") == "442079460958"
