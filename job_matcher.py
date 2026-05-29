"""Job fit scoring against a candidate skill profile."""

from __future__ import annotations

import re
from typing import Iterable, List, Set


def _normalize_skill(skill: str) -> str:
    return re.sub(r"\s+", " ", skill.strip().lower())


def normalize_skills(skills: Iterable[str]) -> Set[str]:
    """Normalize skill strings for comparison."""
    normalized: Set[str] = set()
    for skill in skills:
        cleaned = _normalize_skill(skill)
        if cleaned:
            normalized.add(cleaned)
    return normalized


def compute_match_score(job_skills: Iterable[str], profile_skills: Iterable[str]) -> float:
    """Return overlap ratio between job skills and profile skills (0.0–1.0)."""
    job_set = normalize_skills(job_skills)
    profile_set = normalize_skills(profile_skills)

    if not job_set:
        return 1.0 if not profile_set else 0.0
    if not profile_set:
        return 0.0

    overlap = job_set.intersection(profile_set)
    return round(len(overlap) / len(job_set), 3)


def matched_skills(job_skills: Iterable[str], profile_skills: Iterable[str]) -> List[str]:
    """Return sorted list of skills present in both job and profile."""
    job_set = normalize_skills(job_skills)
    profile_set = normalize_skills(profile_skills)
    return sorted(job_set.intersection(profile_set))


def missing_skills(job_skills: Iterable[str], profile_skills: Iterable[str]) -> List[str]:
    """Return sorted list of job skills not found in the profile."""
    job_set = normalize_skills(job_skills)
    profile_set = normalize_skills(profile_skills)
    return sorted(job_set.difference(profile_set))
