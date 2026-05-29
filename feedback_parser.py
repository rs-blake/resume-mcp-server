"""Parse ResumeUp report feedback and resumefeedback.txt exports."""

import re
from typing import Dict, List, Optional

from models import FeedbackIssue, ResumeFeedback
from utils import find_resume_score

INDEX_SCORE_PATTERN = re.compile(
    r"(Must-Have Sections|Job Description Tailoring|Spelling[,\s]+Grammar(?:\s*&\s*Readability)?|Recruiter Checks)"
    r"[^\d]{0,40}(\d{1,3})\s*%",
    re.I,
)

ISSUE_HEADER_PATTERN = re.compile(
    r"^(Grammar|Spelling|Number of Bullet Points|Content Readability|Passive Voice|"
    r"Job Description Tailoring|Recruiter Checks|Education|Summary|Work Experience)"
    r"(?:\s*[—\-]\s*(.+))?$",
    re.I | re.M,
)

FIXABLE_MARKERS = (
    "fix with ai",
    "correct",
    "too many bullet",
    "readability",
    "grammar",
    "spelling",
    "tailoring",
    "passive voice",
)


def _issue_is_fixable(title: str, description: str) -> bool:
    combined = f"{title} {description}".lower()
    return any(marker in combined for marker in FIXABLE_MARKERS)


def _severity_from_text(title: str, description: str) -> str:
    combined = f"{title} {description}".lower()
    if any(token in combined for token in ("error", "missing", "required", "must")):
        return "error"
    if any(token in combined for token in ("warning", "too many", "improve", "issue")):
        return "warning"
    return "info"


def parse_index_scores(text: str) -> Dict[str, int]:
    """Extract index section scores from report text."""
    scores: Dict[str, int] = {}
    for match in INDEX_SCORE_PATTERN.finditer(text):
        label = match.group(1).strip()
        score = int(match.group(2))
        if 0 <= score <= 100:
            scores[label] = score
    return scores


def parse_feedback_blocks(text: str) -> List[FeedbackIssue]:
    """Parse free-form feedback text into structured issues."""
    issues: List[FeedbackIssue] = []
    if not text.strip():
        return issues

    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        header_match = ISSUE_HEADER_PATTERN.match(lines[0])
        if header_match:
            category = header_match.group(1).title()
            section = header_match.group(2).strip() if header_match.group(2) else None
            description = " ".join(lines[1:]) if len(lines) > 1 else lines[0]
            title = lines[0]
        else:
            category = "General"
            section = None
            title = lines[0][:120]
            description = " ".join(lines)

        suggested_fix = None
        correction_match = re.search(
            r"(?:change|replace|use)\s+[`\"']?(.+?)[`\"']?\s+(?:to|with)\s+[`\"']?(.+?)[`\"']?(?:\.|$)",
            description,
            re.I,
        )
        if correction_match:
            suggested_fix = f"{correction_match.group(1)} -> {correction_match.group(2)}"

        issues.append(
            FeedbackIssue(
                category=category,
                title=title,
                description=description,
                severity=_severity_from_text(title, description),
                section=section,
                fixable_with_ai=_issue_is_fixable(title, description),
                suggested_fix=suggested_fix,
            )
        )

    return issues


def parse_feedback_text(text: str, score: Optional[int] = None) -> ResumeFeedback:
    """Parse feedback exported from ResumeUp or scraped from the Report tab."""
    resolved_score = score if score is not None else find_resume_score_from_text(text)
    return ResumeFeedback(
        score=resolved_score,
        issues=parse_feedback_blocks(text),
        index_scores=parse_index_scores(text),
        raw_text=text,
    )


def find_resume_score_from_text(text: str) -> Optional[int]:
    """Parse score from plain text without a browser page."""

    class _TextPage:
        def inner_text(self, _selector: str) -> str:
            return text

    return find_resume_score(_TextPage())


def format_feedback_for_prompt(feedback: ResumeFeedback) -> str:
    """Format structured feedback for LLM prompt injection."""
    lines: List[str] = []

    if feedback.score is not None:
        lines.append(f"Current resume score: {feedback.score}/100")

    if feedback.index_scores:
        lines.append("Index scores:")
        for label, score in feedback.index_scores.items():
            lines.append(f"- {label}: {score}%")

    if feedback.issues:
        lines.append("Issues to fix:")
        for index, issue in enumerate(feedback.issues, start=1):
            section = f" ({issue.section})" if issue.section else ""
            lines.append(f"{index}. [{issue.category}] {issue.title}{section}")
            lines.append(f"   {issue.description}")
            if issue.suggested_fix:
                lines.append(f"   Suggested fix: {issue.suggested_fix}")

    if not lines:
        lines.append("No explicit issues detected. Improve keyword alignment with the job description.")

    return "\n".join(lines)
