"""Tests for feedback parsing and prompt generation."""

from feedback_parser import (
    format_feedback_for_prompt,
    parse_feedback_text,
    parse_index_scores,
)
from generate_resume import build_improvement_prompt, load_prompt_instructions


SAMPLE_FEEDBACK = """
Resume Score: 79/100

Job Description Tailoring: 85%
Spelling, Grammar & Readability: 75%

Number of Bullet Points — Work Experience — Oak Ridge National Laboratory
This section has 11 bullet points. Recommended range is 3 to 6.
Fix with AI

Content Readability — Summary
The summary is too long for recruiters and ATS scanning.
Fix with AI
"""


def test_parse_index_scores():
    scores = parse_index_scores(SAMPLE_FEEDBACK)
    assert scores["Job Description Tailoring"] == 85
    assert scores["Spelling, Grammar & Readability"] == 75


def test_parse_feedback_text():
    feedback = parse_feedback_text(SAMPLE_FEEDBACK)
    assert feedback.score == 79
    assert len(feedback.issues) >= 2
    assert any(issue.fixable_with_ai for issue in feedback.issues)


def test_format_feedback_for_prompt():
    feedback = parse_feedback_text(SAMPLE_FEEDBACK)
    prompt_section = format_feedback_for_prompt(feedback)
    assert "79/100" in prompt_section
    assert "Issues to fix" in prompt_section


def test_build_improvement_prompt():
    feedback = parse_feedback_text(SAMPLE_FEEDBACK)
    prompt = build_improvement_prompt(
        resume_text="SUMMARY\nExperienced architect...",
        job_description="Solutions Architect role requiring AWS and Kubernetes.",
        feedback=feedback,
        instructions_path="examples/prompinstructions.txt",
    )
    assert "Solutions Architect" in prompt
    assert "Experienced architect" in prompt
    assert "79/100" in prompt


def test_load_prompt_instructions_default():
    instructions = load_prompt_instructions("examples/prompinstructions.txt")
    assert "{job_description}" in instructions
    assert "{feedback}" in instructions
