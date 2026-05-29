"""Unit tests for job_matcher."""

from job_matcher import compute_match_score, matched_skills, missing_skills


def test_compute_match_score_full_overlap():
    score = compute_match_score(["AWS", "Python"], ["aws", "python", "docker"])
    assert score == 1.0


def test_compute_match_score_partial_overlap():
    score = compute_match_score(["AWS", "Python", "Kubernetes"], ["AWS", "Java"])
    assert score == round(1 / 3, 3)


def test_compute_match_score_no_profile_skills():
    score = compute_match_score(["AWS"], [])
    assert score == 0.0


def test_matched_and_missing_skills():
    job = ["AWS", "Python", "Kubernetes"]
    profile = ["aws", "java"]
    assert matched_skills(job, profile) == ["aws"]
    assert missing_skills(job, profile) == ["kubernetes", "python"]
