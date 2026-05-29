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
class JobListing:
    """Summary of a job from LinkedIn search results."""

    job_id: str
    title: str
    company: str
    location: str
    url: str
    easy_apply: bool
    posted_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "easy_apply": self.easy_apply,
            "posted_time": self.posted_time,
        }


@dataclass
class JobDetails:
    """Full job posting details scraped from LinkedIn."""

    job_id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    easy_apply: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "description": self.description,
            "easy_apply": self.easy_apply,
        }


@dataclass
class JobApplication:
    """Tracked job in the review / application queue."""

    application_id: str
    job_id: str
    job_url: str
    title: str
    company: str
    location: str
    status: str
    easy_apply: bool = False
    match_score: Optional[float] = None
    resume_score: Optional[int] = None
    pdf_path: Optional[str] = None
    job_description_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "application_id": self.application_id,
            "job_id": self.job_id,
            "job_url": self.job_url,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "status": self.status,
            "easy_apply": self.easy_apply,
            "match_score": self.match_score,
            "resume_score": self.resume_score,
            "pdf_path": self.pdf_path,
            "job_description_path": self.job_description_path,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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
