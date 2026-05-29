"""Project constants and configuration defaults."""

import os
from pathlib import Path

LOGIN_URL = "https://app.resumeup.ai/signin"
APP_URL = "https://app.resumeup.ai/"
DEFAULT_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "120"))
SESSION_DIR = Path(
    os.path.expanduser(os.getenv("RESUMEUP_SESSION_DIR", "~/.resumeup_automation"))
)
VIEWPORT_WIDTH = 1366
VIEWPORT_HEIGHT = 768
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60

BUTTON_PATTERNS = {
    "resume_upload": [
        r"upload\s+resume",
        r"import\s+resume",
        r"upload\s+from\s+computer",
        r"choose\s+file",
        r"browse",
    ],
    "tailor": [
        r"tailor\s+to\s+jd",
        r"build\s+tailored\s+resume",
        r"build\s+resume",
    ],
    "analyze": [
        r"re-?analyse",
        r"re-?analyze",
        r"analyze",
        r"check\s+score",
        r"run\s+analysis",
        r"update\s+score",
    ],
    "continue_editing": [
        r"continue\s+editing\s+here",
        r"continue\s+editing",
    ],
}

SCORE_PATTERNS = [
    r"resume\s+score\s*:?\s*(\d{1,3})\s*%?",
    r"(\d{1,3})\s*/\s*100",
    r"(\d{1,3})\s*%\s*(?:match|score|fit)?",
    r"(?:match|score|fit)\s*:?\s*(\d{1,3})\s*%?",
]
