"""Unit tests for application_profile."""

import json
from pathlib import Path

from application_profile import (
    load_application_profile,
    profile_as_flat_strings,
    validate_profile_for_apply,
)


def test_load_application_profile_from_file(tmp_path: Path, monkeypatch):
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        json.dumps(
            {
                "contact": {"email": "test@example.com"},
                "work_authorization": "Yes",
                "screening_answers": {"salary": "120000"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("APPLICATION_PROFILE_PATH", str(profile_file))

    profile = load_application_profile()
    assert profile["contact"]["email"] == "test@example.com"
    assert profile["work_authorization"] == "Yes"


def test_profile_as_flat_strings():
    profile = {
        "contact": {"phone": "+1-555-0100"},
        "work_authorization": "Yes",
        "screening_answers": {"salary": "150000"},
    }
    flat = profile_as_flat_strings(profile)
    assert flat["phone"] == "+1-555-0100"
    assert flat["work_authorization"] == "Yes"
    assert flat["salary"] == "150000"


def test_validate_profile_for_apply():
    missing = validate_profile_for_apply({"contact": {}})
    assert "contact.email" in missing
    assert "work_authorization" in missing
