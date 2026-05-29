"""Data models for the ResumeUp MCP server."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time


@dataclass
class JobRequirements:
    """Structured job description data extracted by the parser."""

    title: str
    company: Optional[str]
    key_skills: List[str]
    requirements: List[str]
    nice_to_haves: List[str]
    full_text: str


@dataclass
class ResumeData:
    """Resume metadata captured after upload."""

    id: str
    text: str
    preview: str
    file_path: str
    uploaded_at: float


@dataclass
class FeedbackIssue:
    """Single resume improvement issue from Report tab or feedback file."""

    category: str
    title: str
    description: str
    severity: str = "warning"
    section: Optional[str] = None
    fixable_with_ai: bool = False
    suggested_fix: Optional[str] = None


@dataclass
class ResumeFeedback:
    """Structured feedback extracted from ResumeUp analysis."""

    score: Optional[int]
    issues: List[FeedbackIssue]
    index_scores: Dict[str, int] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize feedback for MCP tool responses."""
        return {
            "score": self.score,
            "index_scores": self.index_scores,
            "issues": [
                {
                    "category": issue.category,
                    "title": issue.title,
                    "description": issue.description,
                    "severity": issue.severity,
                    "section": issue.section,
                    "fixable_with_ai": issue.fixable_with_ai,
                    "suggested_fix": issue.suggested_fix,
                }
                for issue in self.issues
            ],
        }


@dataclass
class BrowserSession:
    """Active Playwright browser session state."""

    session_id: str
    processor: Any
    handler: Any
    resume_data: Optional[ResumeData] = None
    resume_id: Optional[str] = None
    job_description_text: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last accessed timestamp."""
        self.last_accessed = time.time()
