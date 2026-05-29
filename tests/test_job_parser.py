"""Unit tests for job_parser."""

from job_parser import (
    extract_company,
    extract_job_title,
    extract_skills_from_text,
    parse_job_description,
    parse_requirements_list,
)


SAMPLE_JOB = """
Security Architect

Company: Acme Security Corp

Requirements:
- 3+ years of experience in security architecture
- Strong knowledge of AWS and Azure
- Experience with Kubernetes

Nice to have:
- Terraform infrastructure as code
- Python automation experience

Skills: AWS, Azure, Kubernetes, Docker, SIEM
"""


def test_extract_job_title_from_first_line():
    title = extract_job_title("Senior Python Developer\n\nAbout the role...")
    assert title == "Senior Python Developer"


def test_extract_job_title_from_label():
    text = "Job Title: Cloud Engineer\n\nWe are hiring..."
    assert extract_job_title(text) == "Cloud Engineer"


def test_extract_company():
    text = "Company: Acme Corp\n\nJoin our team..."
    assert extract_company(text) == "Acme Corp"


def test_extract_skills_from_text():
    skills = extract_skills_from_text(
        "Must know AWS, kubernetes, and SIEM platforms."
    )
    assert "AWS" in skills
    assert any("kubernetes" in skill.lower() for skill in skills)


def test_parse_requirements_list():
    text = """
    - 3+ years experience
    - AWS knowledge
    - Strong communication skills
    """
    requirements = parse_requirements_list(text)
    assert len(requirements) >= 2
    assert any("AWS" in req for req in requirements)


def test_parse_job_description():
    parsed = parse_job_description(SAMPLE_JOB)
    assert parsed.title == "Security Architect"
    assert parsed.company == "Acme Security Corp"
    assert "AWS" in parsed.key_skills
    assert len(parsed.requirements) >= 1
    assert parsed.full_text == SAMPLE_JOB
