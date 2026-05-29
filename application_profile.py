"""Load and normalize candidate profile for Easy Apply."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


ProfileValue = Union[str, Dict[str, str], List[str]]


def _expand_user(path: str) -> Path:
    return Path(os.path.expanduser(path))


def default_profile_path() -> Path:
    configured = os.getenv("APPLICATION_PROFILE_PATH", "examples/application_profile.json")
    return _expand_user(configured)


def load_application_profile(path: Optional[str] = None) -> Dict[str, Any]:
    """Load profile JSON and merge with environment fallbacks."""
    profile_path = _expand_user(path) if path else default_profile_path()
    profile: Dict[str, Any] = {}

    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))

    contact = profile.setdefault("contact", {})
    if not contact.get("email"):
        contact["email"] = os.getenv("PROFILE_EMAIL", os.getenv("LINKEDIN_EMAIL", ""))
    if not contact.get("phone"):
        contact["phone"] = os.getenv("PROFILE_PHONE", "")

    defaults = {
        "work_authorization": os.getenv("PROFILE_WORK_AUTHORIZATION", "Yes"),
        "requires_sponsorship": os.getenv("PROFILE_REQUIRES_SPONSORSHIP", "No"),
        "years_experience": os.getenv("PROFILE_YEARS_EXPERIENCE", ""),
        "salary_expectation": os.getenv("PROFILE_SALARY_EXPECTATION", ""),
        "salary_currency": os.getenv("PROFILE_SALARY_CURRENCY", "USD"),
        "notice_period_days": os.getenv("PROFILE_NOTICE_PERIOD_DAYS", ""),
        "willing_to_relocate": os.getenv("PROFILE_WILLING_TO_RELOCATE", "Yes"),
        "has_security_clearance": os.getenv("PROFILE_HAS_CLEARANCE", "No"),
    }
    for key, value in defaults.items():
        if key not in profile and value:
            profile[key] = value

    profile.setdefault("screening_answers", {})
    profile.setdefault("default_text_answers", {})
    return profile


def profile_as_flat_strings(profile: Dict[str, Any]) -> Dict[str, str]:
    """Flatten profile into string key/value pairs for form filling."""
    flat: Dict[str, str] = {}

    contact = profile.get("contact", {})
    if isinstance(contact, dict):
        for key, value in contact.items():
            if value:
                flat[key] = str(value)

    scalar_keys = [
        "work_authorization",
        "requires_sponsorship",
        "years_experience",
        "salary_expectation",
        "salary_currency",
        "notice_period_days",
        "willing_to_relocate",
        "has_security_clearance",
        "linkedin_url",
        "portfolio_url",
        "github_url",
    ]
    for key in scalar_keys:
        value = profile.get(key)
        if value:
            flat[key] = str(value)

    screening = profile.get("screening_answers", {})
    if isinstance(screening, dict):
        for key, value in screening.items():
            if value:
                flat[key] = str(value)

    return flat


def validate_profile_for_apply(profile: Dict[str, Any]) -> List[str]:
    """Return list of missing recommended profile fields."""
    missing: List[str] = []
    contact = profile.get("contact", {})
    if not contact.get("email"):
        missing.append("contact.email")
    if not profile.get("work_authorization"):
        missing.append("work_authorization")
    if not profile.get("requires_sponsorship"):
        missing.append("requires_sponsorship")
    return missing
