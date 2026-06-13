from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

_PROFILES_DIR = Path(__file__).parent / "profiles"


@dataclass(frozen=True)
class SchemaProfile:
    version: int
    description: str
    required_tables: dict[str, list[str]]
    size_queries: dict[str, str]


class UnknownSchemaVersion(Exception):
    def __init__(self, version: int, known: list[int]) -> None:
        self.version = version
        self.known = sorted(known)
        known_str = ", ".join(str(v) for v in self.known)
        super().__init__(
            f"Signal DB schema version {version} is not recognized.\n"
            f"Supported versions: {known_str}\n"
            f"To add support: copy src/signalstripper/schema/profiles/v{self.known[-1] if self.known else 'X'}.toml "
            f"→ v{version}.toml and verify column lists against your DB."
        )


def load_profiles() -> dict[int, SchemaProfile]:
    profiles: dict[int, SchemaProfile] = {}
    for path in sorted(_PROFILES_DIR.glob("*.toml")):
        with open(path, "rb") as f:
            data = tomllib.load(f)
        version = int(data["version"])
        profiles[version] = SchemaProfile(
            version=version,
            description=data.get("description", ""),
            required_tables={
                table: list(cols)
                for table, cols in data.get("required_tables", {}).items()
            },
            size_queries={k: v for k, v in data.get("size_queries", {}).items()},
        )
    return profiles


def select_profile(db_version: int, profiles: dict[int, SchemaProfile]) -> SchemaProfile:
    if db_version in profiles:
        return profiles[db_version]
    raise UnknownSchemaVersion(db_version, list(profiles.keys()))
