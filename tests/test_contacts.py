from ingest.contacts import read_contacts
from tests.fixtures import make_addressbook_db


def test_reads_phones_and_emails_normalized(tmp_path):
    make_addressbook_db(
        tmp_path / "Sources" / "abc" / "AddressBook-v22.abcddb",
        people=[
            ("Alice", "Smith", ["+1 (555) 123-4567"], ["Alice@Example.com"]),
            ("Bob", None, ["555-999-0000"], []),
        ],
    )
    contacts = read_contacts(tmp_path)
    assert contacts["5551234567"] == "Alice Smith"
    assert contacts["alice@example.com"] == "Alice Smith"
    assert contacts["5559990000"] == "Bob"


def test_multiple_sources_merged_first_wins(tmp_path):
    make_addressbook_db(tmp_path / "Sources" / "a" / "AddressBook-v22.abcddb",
                        people=[("Alice", "Smith", ["5551234567"], [])])
    make_addressbook_db(tmp_path / "Sources" / "b" / "AddressBook-v22.abcddb",
                        people=[("Alicia", "S", ["5551234567"], [])])
    contacts = read_contacts(tmp_path)
    assert contacts["5551234567"] in ("Alice Smith", "Alicia S")  # deterministic per sort


def test_empty_dir(tmp_path):
    assert read_contacts(tmp_path) == {}
