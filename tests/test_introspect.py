import sqlite3
import pytest
from pathlib import Path
from signalstripper.schema.registry import load_profiles
from signalstripper.schema.introspect import introspect, SchemaValidationError
from signalstripper.schema.registry import UnknownSchemaVersion

_FULL_SCHEMA = """
    CREATE TABLE recipient (_id INTEGER PRIMARY KEY, phone TEXT, profile_joined_name TEXT, group_id TEXT);
    CREATE TABLE thread (_id INTEGER PRIMARY KEY, recipient_id INTEGER, date INTEGER, snippet TEXT);
    CREATE TABLE sms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, type INTEGER);
    CREATE TABLE mms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, m_type INTEGER);
    CREATE TABLE part (_id INTEGER PRIMARY KEY, mid INTEGER, ct TEXT, data_size INTEGER, unique_id INTEGER);
"""


def test_introspect_happy_path(db_v166):
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    assert result.db_version == 166
    assert result.profile.version == 166


def test_introspect_unknown_version(tmp_path):
    db = tmp_path / "unknown.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 999")
    conn.close()
    profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion):
        introspect(db, profiles)


def test_introspect_missing_table(tmp_path):
    db = tmp_path / "missing_table.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 166")
    conn.executescript("""
        CREATE TABLE recipient (_id INTEGER PRIMARY KEY, phone TEXT, profile_joined_name TEXT, group_id TEXT);
        CREATE TABLE thread (_id INTEGER PRIMARY KEY, recipient_id INTEGER, date INTEGER, snippet TEXT);
        CREATE TABLE sms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, type INTEGER);
        CREATE TABLE mms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, m_type INTEGER);
    """)
    conn.close()
    profiles = load_profiles()
    with pytest.raises(SchemaValidationError) as exc_info:
        introspect(db, profiles)
    assert "part" in exc_info.value.missing_tables


def test_introspect_missing_column(tmp_path):
    db = tmp_path / "missing_col.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 166")
    conn.executescript("""
        CREATE TABLE recipient (_id INTEGER PRIMARY KEY, phone TEXT, profile_joined_name TEXT, group_id TEXT);
        CREATE TABLE thread (_id INTEGER PRIMARY KEY, recipient_id INTEGER, date INTEGER, snippet TEXT);
        CREATE TABLE sms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, type INTEGER);
        CREATE TABLE mms (_id INTEGER PRIMARY KEY, thread_id INTEGER, date INTEGER, body TEXT, m_type INTEGER);
        CREATE TABLE part (_id INTEGER PRIMARY KEY, mid INTEGER, ct TEXT, unique_id INTEGER);
    """)
    # Note: data_size column is absent from part
    conn.close()
    profiles = load_profiles()
    with pytest.raises(SchemaValidationError) as exc_info:
        introspect(db, profiles)
    assert "data_size" in exc_info.value.missing_columns.get("part", [])


def test_introspect_multiple_missing_tables(tmp_path):
    """SchemaValidationError accumulates all missing tables, not just the first."""
    db = tmp_path / "bare.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 166")
    conn.execute("CREATE TABLE recipient (_id INTEGER PRIMARY KEY, phone TEXT, profile_joined_name TEXT, group_id TEXT)")
    conn.close()
    profiles = load_profiles()
    with pytest.raises(SchemaValidationError) as exc_info:
        introspect(db, profiles)
    # thread, sms, mms, part are all missing
    assert len(exc_info.value.missing_tables) >= 3


def test_introspect_warnings_for_extra_tables(db_v166):
    # Add an unexpected table to the copy
    conn = sqlite3.connect(db_v166)
    conn.execute("CREATE TABLE extra_unknown (id INTEGER PRIMARY KEY)")
    conn.close()
    profiles = load_profiles()
    result = introspect(db_v166, profiles)
    assert any("extra_unknown" in w for w in result.warnings)


# ── Version-0 fallback (_read_db_version) ────────────────────────────────────

def test_introspect_fallback_to_keyvalue_table(tmp_path):
    """PRAGMA user_version = 0 falls back to keyvalue.schema_version."""
    db = tmp_path / "fallback.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 0")
    conn.execute("CREATE TABLE keyvalue (key TEXT, value TEXT)")
    conn.execute("INSERT INTO keyvalue VALUES ('schema_version', '166')")
    conn.executescript(_FULL_SCHEMA)
    conn.close()
    profiles = load_profiles()
    result = introspect(db, profiles)
    assert result.db_version == 166


def test_introspect_version_zero_no_fallback_table_raises(tmp_path):
    """PRAGMA = 0 and no fallback table → version stays 0 → UnknownSchemaVersion."""
    db = tmp_path / "zero.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 0")
    conn.close()
    profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion):
        introspect(db, profiles)


def test_introspect_pragma_beats_keyvalue_when_nonzero(tmp_path):
    """Non-zero PRAGMA user_version wins even when keyvalue holds a different version."""
    db = tmp_path / "pragma_wins.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA user_version = 166")
    conn.execute("CREATE TABLE keyvalue (key TEXT, value TEXT)")
    conn.execute("INSERT INTO keyvalue VALUES ('schema_version', '999')")
    conn.executescript(_FULL_SCHEMA)
    conn.close()
    profiles = load_profiles()
    result = introspect(db, profiles)
    assert result.db_version == 166
