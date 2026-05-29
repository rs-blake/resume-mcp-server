"""ResumeUp-only end-to-end tailoring workflows."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from resume_processor import ResumeProcessor
from session_manager import create_session, end_session, get_session
from utils import dismiss_editing_conflict, select_template_if_needed

logger = logging.getLogger(__name__)


def _resolve_credentials(
    email: Optional[str],
    password: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    return (
        email or os.getenv("RESUMEUP_EMAIL"),
        password or os.getenv("RESUMEUP_PASSWORD"),
    )


def _resolve_headless(headless: Optional[bool]) -> bool:
    if headless is not None:
        return headless
    return os.getenv("RESUMEUP_HEADLESS", "false").lower() in {"1", "true", "yes"}


def run_tailor_and_download(
    job_description_text: str,
    session_id: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: Optional[bool] = None,
    file_path: Optional[str] = None,
    resume_id: Optional[str] = None,
    resume_name: Optional[str] = None,
    target_score: int = 95,
    max_attempts: int = 8,
    output_dir: str = ".",
    close_session: bool = False,
) -> Dict[str, Any]:
    """Run the full ResumeUp-only pipeline using ResumeUp's built-in AI."""
    if not job_description_text.strip():
        return {"success": False, "message": "job_description_text is required"}

    created_session = False
    session = get_session(session_id) if session_id else None

    if session is None:
        processor = ResumeProcessor()
        session = create_session(processor, headless=_resolve_headless(headless))
        created_session = True
        session_id = session.session_id

        creds_email, creds_password = _resolve_credentials(email, password)
        if not processor.ensure_logged_in(creds_email, creds_password):
            end_session(session_id)
            return {"success": False, "message": "Failed to authenticate with ResumeUp"}

    try:
        handler = session.handler

        if resume_id:
            if not session.processor.navigate_to_editor(resume_id):
                return {"success": False, "message": f"Failed to open resume: {resume_id}"}
            dismiss_editing_conflict(handler.page)
            session.resume_id = resume_id
        elif file_path:
            path = Path(os.path.expanduser(file_path))
            if not path.exists():
                return {"success": False, "message": f"Resume file not found: {path}"}

            resume_data = handler.upload_resume(path)
            if resume_data is None:
                return {"success": False, "message": "Failed to upload resume"}

            session.resume_data = resume_data
            session.resume_id = resume_data.id
            select_template_if_needed(handler.page, handler.timeout)
            dismiss_editing_conflict(handler.page)

        session.job_description_text = job_description_text.strip()
        if not handler.enter_job_description(job_description_text, resume_name=resume_name):
            return {"success": False, "message": "Failed to enter job description in ResumeUp"}

        final_score, attempts = handler.improve_until_target(
            target_score=target_score,
            max_attempts=max_attempts,
        )

        downloaded = handler.download_resume(
            Path(os.path.expanduser(output_dir)),
            resume_name=resume_name,
        )

        target_reached = final_score is not None and final_score >= target_score
        return {
            "success": downloaded is not None or target_reached,
            "session_id": session_id,
            "target_reached": target_reached,
            "final_score": final_score,
            "attempts_used": attempts,
            "file_path": str(downloaded) if downloaded else None,
            "message": (
                f"Tailoring complete. Score: {final_score}, PDF: {downloaded}"
                if downloaded
                else f"Tailoring complete. Score: {final_score} (download failed)"
            ),
        }
    finally:
        if close_session and (created_session or session_id):
            end_session(session_id)
