import pytest
from pathlib import Path
from signalstripper.schema.registry import load_profiles, select_profile, UnknownSchemaVersion

_PROFILES_DIR = Path(__file__).parent.parent / "src" / "signalstripper" / "schema" / "profiles"


def test_load_profiles_contains_v166():
    profiles = load_profiles()
    assert 166 in profiles


def test_profile_has_required_fields():
    profiles = load_profiles()
    p = profiles[166]
    assert p.version == 166
    assert "sms" in p.required_tables
    assert "_id" in p.required_tables["sms"]
    assert "attachments_by_thread" in p.size_queries


def test_select_profile_known():
    profiles = load_profiles()
    p = select_profile(166, profiles)
    assert p.version == 166
    assert p is profiles[166]  # same object, not a copy


@pytest.mark.parametrize("version,profiles", [
    pytest.param(999,  None, id="unknown-version"),
    pytest.param(0,    None, id="zero-pragma-degenerate"),
    pytest.param(166,  {},   id="empty-profiles-dict"),
])
def test_select_profile_raises(version, profiles):
    if profiles is None:
        profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion):
        select_profile(version, profiles)


def test_unknown_schema_error_message_lists_versions():
    profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion) as exc_info:
        select_profile(999, profiles)
    msg = str(exc_info.value)
    assert "999" in msg
    assert "166" in msg


def test_no_duplicate_versions():
    """Two TOML files with the same version= integer cause silent overwrite — detect it."""
    profiles = load_profiles()
    toml_count = len(list(_PROFILES_DIR.glob("*.toml")))
    assert len(profiles) == toml_count, (
        "Loaded profile count != TOML file count: two files likely share a version integer"
    )
