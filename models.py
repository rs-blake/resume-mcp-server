"""Data models for the ResumeUp MCP server."""

from dataclasses import dataclass, field
from typing import Any, List, Optional
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
class BrowserSession:
    """Active Playwright browser session state."""

    session_id: str
    processor: Any
    handler: Any
    resume_data: Optional[ResumeData] = None
    resume_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last accessed timestamp."""
        self.last_accessed = time.time()
