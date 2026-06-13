import pytest
from signalstripper.schema.registry import load_profiles, select_profile, UnknownSchemaVersion


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


def test_select_profile_unknown_raises():
    profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion) as exc_info:
        select_profile(999, profiles)
    assert exc_info.value.version == 999
    assert 166 in exc_info.value.known


def test_unknown_schema_error_message_lists_versions():
    profiles = load_profiles()
    with pytest.raises(UnknownSchemaVersion) as exc_info:
        select_profile(999, profiles)
    msg = str(exc_info.value)
    assert "999" in msg
    assert "166" in msg


def test_no_duplicate_versions():
    profiles = load_profiles()
    versions = list(profiles.keys())
    assert len(versions) == len(set(versions))
