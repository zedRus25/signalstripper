from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from signalstripper.schema.registry import SchemaProfile, UnknownSchemaVersion, load_profiles, select_profile


class SchemaValidationError(Exception):
    def __init__(self, message: str, missing_tables: list[str] = (), missing_columns: dict[str, list[str]] = {}) -> None:
        self.missing_tables = list(missing_tables)
        self.missing_columns = dict(missing_columns)
        super().__init__(message)


@dataclass
class IntrospectionResult:
    db_version: int
    profile: SchemaProfile
    warnings: list[str] = field(default_factory=list)


def _read_db_version(conn: sqlite3.Connection) -> int:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version != 0:
        return version
    # Fallback: check for a Signal-internal version/settings table (deferred §4.1)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for candidate in ("keyvalue", "key_value", "preferences"):
        if candidate in tables:
            try:
                row = conn.execute(
                    f"SELECT value FROM {candidate} WHERE key = 'schema_version' LIMIT 1"
                ).fetchone()
                if row:
                    return int(row[0])
            except (sqlite3.OperationalError, ValueError):
                pass
    return 0


def _actual_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def introspect(db_path: Path, profiles: dict[int, SchemaProfile] | None = None) -> IntrospectionResult:
    if profiles is None:
        profiles = load_profiles()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        db_version = _read_db_version(conn)

        # Raises UnknownSchemaVersion (fail-closed) if not profiled
        profile = select_profile(db_version, profiles)

        existing_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing_tables = []
        missing_columns: dict[str, list[str]] = {}
        warnings: list[str] = []

        for table, required_cols in profile.required_tables.items():
            if table not in existing_tables:
                missing_tables.append(table)
                continue
            actual = _actual_columns(conn, table)
            absent = [c for c in required_cols if c not in actual]
            if absent:
                missing_columns[table] = absent

        extra_tables = existing_tables - set(profile.required_tables)
        if extra_tables:
            warnings.append(f"Unknown tables (informational): {sorted(extra_tables)}")

        if missing_tables or missing_columns:
            parts = []
            if missing_tables:
                parts.append(f"Missing tables: {missing_tables}")
            if missing_columns:
                parts.append(f"Missing columns: {missing_columns}")
            raise SchemaValidationError(
                "DB schema does not match profile v{}: {}".format(db_version, "; ".join(parts)),
                missing_tables=missing_tables,
                missing_columns=missing_columns,
            )

        return IntrospectionResult(db_version=db_version, profile=profile, warnings=warnings)
    finally:
        conn.close()
