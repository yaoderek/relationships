import sqlite3
from pathlib import Path

from .handles import normalize_handle

_QUERY = """
    SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, p.ZFULLNUMBER AS raw
    FROM ZABCDRECORD r JOIN ZABCDPHONENUMBER p ON p.ZOWNER = r.Z_PK
    UNION ALL
    SELECT r.ZFIRSTNAME, r.ZLASTNAME, r.ZORGANIZATION, e.ZADDRESS AS raw
    FROM ZABCDRECORD r JOIN ZABCDEMAILADDRESS e ON e.ZOWNER = r.Z_PK
"""


def read_contacts(addressbook_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for db in sorted(addressbook_dir.glob("**/AddressBook-v22.abcddb")):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for first, last, org, raw in conn.execute(_QUERY):
                if not raw:
                    continue
                name = " ".join(part for part in (first, last) if part) or org
                if name:
                    mapping.setdefault(normalize_handle(raw), name)
        finally:
            conn.close()
    return mapping
