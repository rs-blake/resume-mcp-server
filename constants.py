"""Project constants and configuration defaults."""

import os
from pathlib import Path

LOGIN_URL = "https://app.resumeup.ai/signin"
APP_URL = "https://app.resumeup.ai/"
DEFAULT_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "120"))
SESSION_DIR = Path(
    os.path.expanduser(os.getenv("RESUMEUP_SESSION_DIR", "~/.resumeup_automation"))
)
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60

# LinkedIn automation
LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"
LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/"
LINKEDIN_SESSION_DIR = Path(
    os.path.expanduser(os.getenv("LINKEDIN_SESSION_DIR", "~/.linkedin_automation"))
)
LINKEDIN_DEFAULT_TIMEOUT = int(os.getenv("LINKEDIN_TIMEOUT", "120"))
APPLICATIONS_OUTPUT_DIR = Path(
    os.path.expanduser(os.getenv("APPLICATIONS_OUTPUT_DIR", "~/applications"))
)

# LinkedIn job search filter codes (f_* query params)
LINKEDIN_FILTER_EASY_APPLY = "f_AL"
LINKEDIN_FILTER_REMOTE = "f_WT"
LINKEDIN_REMOTE_VALUE = "2"

# Pipeline tuning defaults (override via env)
DEFAULT_MIN_MATCH_SCORE = float(os.getenv("DEFAULT_MIN_MATCH_SCORE", "0.35"))
DEFAULT_SEARCH_LIMIT = int(os.getenv("DEFAULT_SEARCH_LIMIT", "5"))
DAILY_TAILOR_CAP = int(os.getenv("DAILY_TAILOR_CAP", "10"))
DEFAULT_MAX_CUSTOM_QUESTIONS = int(os.getenv("MAX_CUSTOM_QUESTIONS", "5"))
USE_LLM_SCREENING = os.getenv("USE_LLM_SCREENING", "true").lower() in {"1", "true", "yes"}

BUTTON_PATTERNS = {
    "resume_upload": [
        r"upload resume",
        r"import resume",
        r"add resume",
        r"use existing resume",
        r"resume upload",
        r"upload\s+resume",
        r"upload\s+from\s+computer",
    ],
    "job_upload": [
        r"upload job description",
        r"upload jd",
        r"import job description",
        r"add job description",
        r"job description",
        r"tailor to job",
        r"target job",
    ],
    "tailor": [
        r"tailor\s+to\s+jd",
        r"build\s+tailored\s+resume",
        r"build\s+resume",
    ],
    "analyze": [
        r"analyze",
        r"score",
        r"optimize",
        r"review",
        r"check score",
        r"improve",
        r"re-?analyse",
        r"re-?analyze",
    ],
    "analyze_my_resume": [
        r"analyze\.my\.resume",
    ],
    "ai_suggestion": [
        r"fix\.with\.ai",
        r"add\.with\.ai",
        r"add\.all\.to\.skills",
    ],
    "continue_editing": [
        r"continue editing here",
        r"continue\s+editing",
    ],
}

SCORE_PATTERNS = [
    r"(?:re-analy|resume.?score)[^\d]{0,60}(\d{2,3})",
    r"score[^\d]{0,20}(\d{1,3})",
    r"(\d{2,3})\s*/\s*100",
    r"(\d{2,3})\s*pts",
    r"(\d{2,3})\s*%",
    r"resume\s+score\s*:?\s*(\d{1,3})\s*%?",
]

TEMPLATE_PATTERNS = [
    r"ATS.Friendly",
    r"ATS Friendly",
    r"Craft",
    r"Catalyst",
    r"Luminary",
    r"Standard",
    r"Classic",
    r"Elegant",
    r"Use Template",
    r"Use This",
    r"Continue",
    r"Next",
]
