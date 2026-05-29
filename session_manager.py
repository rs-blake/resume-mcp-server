"""Browser session lifecycle management."""

import logging
import time
import uuid
from typing import Dict, Optional

from constants import SESSION_MAX_AGE_SECONDS
from models import BrowserSession
from resume_processor import ResumeProcessor
from resumeup_tools import ResumeUpHandler

logger = logging.getLogger(__name__)

_sessions: Dict[str, BrowserSession] = {}


def cleanup_stale_sessions(max_age_seconds: int = SESSION_MAX_AGE_SECONDS) -> int:
    """Close sessions inactive longer than max_age_seconds."""
    now = time.time()
    stale_ids = [
        session_id
        for session_id, session in _sessions.items()
        if now - session.last_accessed > max_age_seconds
    ]

    for session_id in stale_ids:
        logger.info("Cleaning up stale session: %s", session_id)
        end_session(session_id)

    return len(stale_ids)


def create_session(
    processor: ResumeProcessor,
    headless: bool = False,
) -> BrowserSession:
    """Initialize browser resources and register a new session."""
    cleanup_stale_sessions()

    processor.init_browser(headless=headless)
    handler = ResumeUpHandler(processor.page, processor.timeout)

    session = BrowserSession(
        session_id=str(uuid.uuid4()),
        processor=processor,
        handler=handler,
    )
    _sessions[session.session_id] = session
    logger.info("Created session: %s", session.session_id)
    return session


def get_session(session_id: str) -> Optional[BrowserSession]:
    """Return an active session or None."""
    session = _sessions.get(session_id)
    if session is None:
        return None

    session.touch()
    return session


def end_session(session_id: str) -> bool:
    """Close and remove a session."""
    session = _sessions.pop(session_id, None)
    if session is None:
        return False

    try:
        session.processor.close_browser()
    except Exception as exc:
        logger.error("Error closing session %s: %s", session_id, exc)

    logger.info("Ended session: %s", session_id)
    return True


def list_sessions() -> Dict[str, BrowserSession]:
    """Return all active sessions."""
    return dict(_sessions)
