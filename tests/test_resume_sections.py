"""Tests for resume section parsing."""

from resume_sections import merge_sections, parse_resume_sections

SAMPLE = """
SUMMARY
Experienced cloud security architect with AWS and Kubernetes expertise.

SKILLS
AWS, Azure, Kubernetes

WORK EXPERIENCE
Solutions Architect | Example Corp | 2023 – Present
- Led cloud security POCs
- Improved deployment automation

EDUCATION
Example University
"""


def test_parse_resume_sections():
    sections = parse_resume_sections(SAMPLE)
    assert "Summary" in sections
    assert "Skills" in sections
    assert "Work Experience" in sections
    assert "Education" in sections
    assert "AWS" in sections["Skills"]


def test_parse_resume_without_headers():
    text = "Plain resume body without section headers."
    sections = parse_resume_sections(text)
    assert sections["Summary"] == text


def test_merge_sections():
    base = {"Summary": "Old summary", "Skills": "Python"}
    updates = {"Summary": "New summary", "Education": "State University"}
    merged = merge_sections(base, updates)
    assert merged["Summary"] == "New summary"
    assert merged["Skills"] == "Python"
    assert merged["Education"] == "State University"
