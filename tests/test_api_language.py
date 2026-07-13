from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from server.app import create_app


def test_language_endpoints_503_without_artifacts(client):
    # the canonical fixture has no language.duckdb next to it
    assert client.get("/api/language/topics").status_code == 503
    assert client.get("/api/language/voice").status_code == 503
    assert client.get("/api/language/signature?scope=you").status_code == 503
    assert client.get("/api/language/drift").status_code == 503


@pytest.fixture(scope="module")
def lang_client(analytics_db: Path):
    lang = analytics_db.parent / "language.duckdb"
    con = duckdb.connect(str(lang))
    con.execute("""
        CREATE TABLE clusters (cluster_id INTEGER, label TEXT,
                               msg_count INTEGER, share DOUBLE);
        CREATE TABLE cluster_people (cluster_id INTEGER, name TEXT, share DOUBLE);
        CREATE TABLE voice_person (person_id INTEGER, name TEXT, msgs INTEGER,
                                   divergence DOUBLE, mirroring DOUBLE);
        CREATE TABLE voice_drift (month TEXT, drift DOUBLE, novelty DOUBLE);
        CREATE TABLE signature_phrases (scope TEXT, label TEXT, phrase TEXT,
                                        count INTEGER, score DOUBLE);
        CREATE TABLE person_clusters (cluster_id INTEGER, label TEXT,
                                      person_id INTEGER, name TEXT);
        CREATE TABLE person_map (person_id INTEGER, name TEXT, period TEXT,
                                 x DOUBLE, y DOUBLE, z DOUBLE,
                                 cluster_id INTEGER, msgs INTEGER);
        INSERT INTO clusters VALUES (0, 'plans and logistics', 100, 0.5);
        INSERT INTO cluster_people VALUES (0, 'Alice Smith', 0.6);
        INSERT INTO voice_person VALUES (1, 'Alice Smith', 40, 0.12, 0.83);
        INSERT INTO voice_drift VALUES ('2024-06', NULL, 0.1);
        INSERT INTO signature_phrases VALUES
            ('you', 'You', 'womp womp', 12, 8.5),
            ('person:1', 'Alice Smith', 'rip to bro', 6, 5.2);
        INSERT INTO person_clusters VALUES (0, 'the gym crew', 1, 'Alice Smith');
        INSERT INTO person_map VALUES
            (1, 'Alice Smith', 'all', 0.1, 0.2, 0.3, 0, 40),
            (1, 'Alice Smith', '2024', 0.2, 0.1, 0.4, 0, 20);
    """)
    con.close()
    yield TestClient(create_app(analytics_db))
    lang.unlink()


def test_language_topics(lang_client):
    topics = lang_client.get("/api/language/topics").json()
    assert topics == [{
        "cluster_id": 0, "label": "plans and logistics",
        "msg_count": 100, "share": 0.5,
        "people": [{"name": "Alice Smith", "share": 0.6}],
    }]


def test_language_voice_and_drift(lang_client):
    voice = lang_client.get("/api/language/voice").json()
    assert voice[0]["name"] == "Alice Smith"
    assert voice[0]["mirroring"] == 0.83
    drift = lang_client.get("/api/language/drift").json()
    assert drift == [{"month": "2024-06", "drift": None, "novelty": 0.1}]


def test_people_clusters(lang_client):
    out = lang_client.get("/api/language/people-clusters").json()
    assert out == [{"cluster_id": 0, "label": "the gym crew",
                    "members": [{"person_id": 1, "name": "Alice Smith"}]}]


def test_people_map(lang_client):
    out = lang_client.get("/api/language/people-map").json()
    assert out["periods"] == ["2024", "all"]
    assert out["points"][0]["name"] == "Alice Smith"
    assert {p["period"] for p in out["points"]} == {"all", "2024"}


def test_language_signature_scopes(lang_client):
    you = lang_client.get("/api/language/signature?scope=you").json()
    assert you["phrases"][0]["phrase"] == "womp womp"
    scopes = lang_client.get("/api/language/scopes").json()
    assert {"scope": "person:1", "label": "Alice Smith"} in scopes
