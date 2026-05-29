#!/usr/bin/env python3
"""ResumeUp Resume Tailoring MCP Server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from job_parser import parse_job_description
from application_orchestrator import (
    check_pipeline_setup,
    export_queue_csv,
    get_application_history,
    run_apply_from_queue,
    run_search_and_tailor,
)
from constants import DEFAULT_MIN_MATCH_SCORE, DEFAULT_SEARCH_LIMIT
from application_store import update_application_status
from linkedin_job_scraper import get_job_details
from linkedin_job_search import search_jobs
from linkedin_processor import LinkedInProcessor
from resume_processor import ResumeProcessor
from resumeup_workflow import run_tailor_and_download
from session_manager import create_session, end_session, get_session

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SERVER_NAME = "resumeup-mcp"
server = Server(SERVER_NAME)


def _tool_result(payload: Dict[str, Any]) -> types.CallToolResult:
    """Return a standardized JSON tool response."""
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, indent=2))],
        structuredContent=payload,
    )


def _error(message: str) -> types.CallToolResult:
    """Return a standardized error response."""
    return _tool_result({"success": False, "message": message})


def _require_session(session_id: str):
    """Fetch a session or raise ValueError."""
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id}")
    return session


def _resolve_credentials(
    email: Optional[str],
    password: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve credentials from arguments or environment."""
    return (
        email or os.getenv("RESUMEUP_EMAIL"),
        password or os.getenv("RESUMEUP_PASSWORD"),
    )


def _resolve_headless(headless: Optional[bool]) -> bool:
    """Resolve headless mode from argument or environment."""
    if headless is not None:
        return headless
    return os.getenv("RESUMEUP_HEADLESS", "false").lower() in {"1", "true", "yes"}


def _handle_start_browser_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    email, password = _resolve_credentials(
        arguments.get("email"),
        arguments.get("password"),
    )
    headless = _resolve_headless(arguments.get("headless"))

    processor = ResumeProcessor()
    session = create_session(processor, headless=headless)

    logged_in = processor.ensure_logged_in(email, password)
    if not logged_in:
        end_session(session.session_id)
        return {
            "success": False,
            "message": "Failed to authenticate with ResumeUp",
        }

    return {
        "success": True,
        "session_id": session.session_id,
        "is_logged_in": True,
        "message": "Browser session started and authenticated",
    }


def _handle_upload_resume(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    file_path = arguments.get("file_path")
    resume_id = arguments.get("resume_id")

    if resume_id:
        if not session.processor.navigate_to_editor(resume_id):
            return {
                "success": False,
                "message": f"Failed to navigate to resume: {resume_id}",
            }

        if not session.processor.select_template():
            return {
                "success": False,
                "message": "Failed to open resume editor",
            }

        session.resume_id = resume_id
        return {
            "success": True,
            "resume_id": resume_id,
            "resume_preview": "",
            "message": "Resume opened by ID",
        }

    if not file_path:
        return {
            "success": False,
            "message": "Either file_path or resume_id is required",
        }

    path = Path(os.path.expanduser(file_path))
    if not path.exists():
        return {
            "success": False,
            "message": f"Resume file not found: {path}",
        }

    resume_data = session.handler.upload_resume(path)
    if resume_data is None:
        return {
            "success": False,
            "message": "Failed to upload resume",
        }

    session.resume_data = resume_data
    session.resume_id = resume_data.id

    if not session.processor.select_template():
        return {
            "success": False,
            "message": "Resume uploaded but template selection failed",
        }

    return {
        "success": True,
        "resume_id": resume_data.id,
        "resume_preview": resume_data.preview,
        "message": "Resume uploaded successfully",
    }


def _handle_parse_job_description(arguments: Dict[str, Any]) -> Dict[str, Any]:
    job_text = arguments.get("job_description_text", "").strip()
    if not job_text:
        return {
            "success": False,
            "message": "job_description_text is required",
        }

    parsed = parse_job_description(job_text)
    return {
        "success": True,
        "title": parsed.title,
        "company": parsed.company,
        "key_skills": parsed.key_skills,
        "requirements": parsed.requirements,
        "nice_to_haves": parsed.nice_to_haves,
        "message": f"Parsed job: {parsed.title}",
    }


def _handle_upload_job_to_resumeup(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    job_text = arguments.get("job_description_text", "").strip()
    if not job_text:
        return {
            "success": False,
            "message": "job_description_text is required",
        }

    resume_name = arguments.get("resume_name")
    session.job_description_text = job_text

    if not session.handler.enter_job_description(job_text, resume_name=resume_name):
        return {
            "success": False,
            "message": "Failed to upload job description",
        }

    return {
        "success": True,
        "message": "Job description uploaded successfully",
    }


def _handle_get_resume_score(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    score = session.handler.get_score()

    if score is None:
        return {
            "success": True,
            "score": None,
            "found": False,
            "message": "Resume score not found",
        }

    return {
        "success": True,
        "score": score,
        "found": True,
        "message": f"Resume score: {score}",
    }


def _handle_trigger_analysis(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    if not session.handler.trigger_analysis():
        return {
            "success": False,
            "message": "Failed to trigger analysis",
        }

    return {
        "success": True,
        "message": "Analysis triggered successfully",
    }


def _handle_poll_score_until_target(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    target_score = int(arguments.get("target_score", 95))
    max_attempts = int(arguments.get("max_attempts", 8))
    wait_between = int(arguments.get("wait_between_attempts_sec", 8))

    final_score, attempts_used = session.handler.poll_score_until_target(
        target_score=target_score,
        max_attempts=max_attempts,
        wait_between_attempts=wait_between,
    )

    if final_score is None:
        return {
            "success": False,
            "final_score": None,
            "target_reached": False,
            "attempts_used": attempts_used,
            "message": "Polling failed before reaching target score",
        }

    return {
        "success": True,
        "final_score": final_score,
        "target_reached": final_score >= target_score,
        "attempts_used": attempts_used,
        "message": f"Polling complete. Final score: {final_score}",
    }


def _handle_download_tailored_resume(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    output_dir = Path(os.path.expanduser(arguments.get("output_dir", ".")))

    resume_name = arguments.get("resume_name")
    downloaded = session.handler.download_resume(output_dir, resume_name=resume_name)
    if downloaded is None:
        return {
            "success": False,
            "message": "Failed to download tailored resume",
        }

    return {
        "success": True,
        "file_path": str(downloaded),
        "message": f"Resume downloaded: {downloaded}",
    }



def _handle_get_resume_feedback(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    feedback = session.handler.get_report_feedback()
    return {
        "success": True,
        "feedback": feedback.to_dict(),
        "message": f"Found {len(feedback.issues)} issue(s)",
    }



def _handle_apply_ai_fixes(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    max_fixes = int(arguments.get("max_fixes", 5))
    fixes_applied = session.handler.apply_ai_fixes(max_fixes=max_fixes)

    if fixes_applied == 0:
        return {
            "success": False,
            "fixes_applied": 0,
            "message": "No Fix with AI buttons were found",
        }

    if arguments.get("trigger_analysis", True):
        session.handler.trigger_analysis()

    score = session.handler.get_score()
    return {
        "success": True,
        "fixes_applied": fixes_applied,
        "score": score,
        "message": f"Applied {fixes_applied} AI fix(es)",
    }


def _handle_improve_resume_until_target(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session = _require_session(arguments["session_id"])
    target_score = int(arguments.get("target_score", 95))
    max_attempts = int(arguments.get("max_rounds", arguments.get("max_attempts", 8)))
    wait_between = int(arguments.get("wait_between_rounds_sec", 8))

    final_score, attempts = session.handler.improve_until_target(
        target_score=target_score,
        max_attempts=max_attempts,
        wait_between_attempts=wait_between,
    )

    return {
        "success": final_score is not None,
        "target_reached": bool(final_score is not None and final_score >= target_score),
        "final_score": final_score,
        "attempts_used": attempts,
        "message": f"Improvement complete. Final score: {final_score}",
    }




def _handle_tailor_and_download(arguments: Dict[str, Any]) -> Dict[str, Any]:
    job_text = (arguments.get("job_description_text") or "").strip()
    if not job_text and arguments.get("job_desc_file"):
        job_text = Path(os.path.expanduser(arguments["job_desc_file"])).read_text(encoding="utf-8").strip()

    return run_tailor_and_download(
        job_description_text=job_text,
        session_id=arguments.get("session_id"),
        email=arguments.get("email"),
        password=arguments.get("password"),
        headless=arguments.get("headless"),
        file_path=arguments.get("file_path"),
        resume_id=arguments.get("resume_id"),
        resume_name=arguments.get("resume_name"),
        target_score=int(arguments.get("target_score", 95)),
        max_attempts=int(arguments.get("max_attempts", 8)),
        output_dir=arguments.get("output_dir", "."),
        close_session=bool(arguments.get("close_session", False)),
    )

def _handle_end_browser_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    session_id = arguments["session_id"]
    if not end_session(session_id):
        return {
            "success": False,
            "message": f"Session not found: {session_id}",
        }

    return {
        "success": True,
        "message": f"Session closed: {session_id}",
    }


def _run_with_linkedin(arguments: Dict[str, Any], callback):
    """Initialize LinkedIn browser, authenticate, and run callback."""
    linkedin = LinkedInProcessor()
    headless = _resolve_headless(arguments.get("headless"))
    if arguments.get("headless") is None:
        headless = os.getenv("LINKEDIN_HEADLESS", "false").lower() in {"1", "true", "yes"}

    close_session = bool(arguments.get("close_linkedin_session", True))
    try:
        linkedin.init_browser(headless=headless)
        email = arguments.get("linkedin_email") or os.getenv("LINKEDIN_EMAIL")
        password = arguments.get("linkedin_password") or os.getenv("LINKEDIN_PASSWORD")
        if not linkedin.ensure_logged_in(email, password):
            return {"success": False, "message": "Failed to authenticate with LinkedIn"}
        return callback(linkedin)
    finally:
        if close_session:
            linkedin.close_browser()


def _handle_linkedin_search_jobs(arguments: Dict[str, Any]) -> Dict[str, Any]:
    keywords = (arguments.get("keywords") or "").strip()
    if not keywords:
        return {"success": False, "message": "keywords is required"}

    def _search(linkedin: LinkedInProcessor) -> Dict[str, Any]:
        listings = search_jobs(
            linkedin,
            keywords=keywords,
            location=arguments.get("location", ""),
            easy_apply_only=bool(arguments.get("easy_apply_only", True)),
            remote_only=bool(arguments.get("remote_only", False)),
            limit=int(arguments.get("limit", 20)),
        )
        return {
            "success": True,
            "count": len(listings),
            "jobs": [job.to_dict() for job in listings],
            "message": f"Found {len(listings)} job listing(s)",
        }

    return _run_with_linkedin(arguments, _search)


def _handle_linkedin_get_job_details(arguments: Dict[str, Any]) -> Dict[str, Any]:
    job_url = (arguments.get("job_url") or "").strip()
    if not job_url:
        return {"success": False, "message": "job_url is required"}

    def _details(linkedin: LinkedInProcessor) -> Dict[str, Any]:
        details = get_job_details(linkedin, job_url)
        if details is None:
            return {"success": False, "message": f"Failed to scrape job details: {job_url}"}
        return {
            "success": True,
            "job": details.to_dict(),
            "message": f"Scraped job: {details.title} at {details.company}",
        }

    return _run_with_linkedin(arguments, _details)


def _handle_search_and_tailor(arguments: Dict[str, Any]) -> Dict[str, Any]:
    keywords = (arguments.get("keywords") or "").strip()
    if not keywords:
        return {"success": False, "message": "keywords is required"}

    profile_skills = arguments.get("profile_skills")
    if isinstance(profile_skills, str):
        profile_skills = [skill.strip() for skill in profile_skills.split(",") if skill.strip()]

    limit_arg = arguments.get("limit")
    min_score_arg = arguments.get("min_match_score")

    return run_search_and_tailor(
        keywords=keywords,
        location=arguments.get("location", ""),
        easy_apply_only=bool(arguments.get("easy_apply_only", True)),
        remote_only=bool(arguments.get("remote_only", False)),
        limit=int(limit_arg) if limit_arg is not None else None,
        min_match_score=float(min_score_arg) if min_score_arg is not None else None,
        profile_skills=profile_skills,
        output_dir=arguments.get("output_dir"),
        resume_session_id=arguments.get("session_id"),
        file_path=arguments.get("file_path"),
        resume_id=arguments.get("resume_id"),
        resume_name=arguments.get("resume_name"),
        target_score=int(arguments.get("target_score", 95)),
        max_attempts=int(arguments.get("max_attempts", 8)),
        daily_cap=int(arguments["daily_cap"]) if arguments.get("daily_cap") is not None else None,
        dedupe_company_title=bool(arguments.get("dedupe_company_title", True)),
        linkedin_email=arguments.get("linkedin_email"),
        linkedin_password=arguments.get("linkedin_password"),
        headless=arguments.get("headless"),
        close_linkedin_session=bool(arguments.get("close_linkedin_session", True)),
    )


def _handle_get_application_history(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return get_application_history(
        status=arguments.get("status"),
        limit=int(arguments.get("limit", 50)),
    )


def _handle_approve_application(arguments: Dict[str, Any]) -> Dict[str, Any]:
    application_id = arguments.get("application_id")
    if not application_id:
        return {"success": False, "message": "application_id is required"}

    application = update_application_status(application_id, "approved")
    if application is None:
        return {"success": False, "message": f"Application not found: {application_id}"}

    return {
        "success": True,
        "application": application.to_dict(),
        "message": f"Application approved: {application.title}",
    }


def _handle_linkedin_easy_apply(arguments: Dict[str, Any]) -> Dict[str, Any]:
    application_id = arguments.get("application_id")
    if not application_id:
        return {"success": False, "message": "application_id is required"}

    max_q = arguments.get("max_custom_questions")
    return run_apply_from_queue(
        application_id=application_id,
        require_approval=bool(arguments.get("require_approval", True)),
        submit=bool(arguments.get("submit", False)),
        max_custom_questions=int(max_q) if max_q is not None else None,
        use_llm=arguments.get("use_llm"),
        linkedin_email=arguments.get("linkedin_email"),
        linkedin_password=arguments.get("linkedin_password"),
        headless=arguments.get("headless"),
        close_linkedin_session=bool(arguments.get("close_linkedin_session", True)),
    )


def _handle_export_applications_csv(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return export_queue_csv(
        output_path=arguments.get("output_path"),
        status=arguments.get("status"),
    )


def _handle_check_pipeline_setup(arguments: Dict[str, Any]) -> Dict[str, Any]:
    return check_pipeline_setup()


TOOL_HANDLERS = {
    "start_browser_session": _handle_start_browser_session,
    "upload_resume": _handle_upload_resume,
    "parse_job_description": _handle_parse_job_description,
    "upload_job_to_resumeup": _handle_upload_job_to_resumeup,
    "get_resume_score": _handle_get_resume_score,
    "trigger_analysis": _handle_trigger_analysis,
    "poll_score_until_target": _handle_poll_score_until_target,
    "download_tailored_resume": _handle_download_tailored_resume,
    "get_resume_feedback": _handle_get_resume_feedback,
    "apply_ai_fixes": _handle_apply_ai_fixes,
    "improve_resume_until_target": _handle_improve_resume_until_target,
    "tailor_and_download": _handle_tailor_and_download,
    "end_browser_session": _handle_end_browser_session,
    "linkedin_search_jobs": _handle_linkedin_search_jobs,
    "linkedin_get_job_details": _handle_linkedin_get_job_details,
    "search_and_tailor": _handle_search_and_tailor,
    "get_application_history": _handle_get_application_history,
    "approve_application": _handle_approve_application,
    "linkedin_easy_apply": _handle_linkedin_easy_apply,
    "export_applications_csv": _handle_export_applications_csv,
    "check_pipeline_setup": _handle_check_pipeline_setup,
}


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Expose all ResumeUp automation tools."""
    return [
        types.Tool(
            name="start_browser_session",
            description="Start a browser session and authenticate with ResumeUp.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "ResumeUp email"},
                    "password": {"type": "string", "description": "ResumeUp password"},
                    "headless": {"type": "boolean", "description": "Run browser headless"},
                },
            },
        ),
        types.Tool(
            name="upload_resume",
            description="Upload a resume file or open an existing resume by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "file_path": {"type": "string"},
                    "resume_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="parse_job_description",
            description="Parse a job description into structured fields.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_description_text": {"type": "string"},
                },
                "required": ["job_description_text"],
            },
        ),
        types.Tool(
            name="upload_job_to_resumeup",
            description="Enter a job description in ResumeUp's Report tab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "job_description_text": {"type": "string"},
                    "resume_name": {"type": "string", "description": "Partial dashboard resume name"},
                },
                "required": ["session_id", "job_description_text"],
            },
        ),
        types.Tool(
            name="get_resume_score",
            description="Fetch the current resume score from ResumeUp.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="trigger_analysis",
            description="Trigger a resume re-analysis in ResumeUp.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="poll_score_until_target",
            description="Repeatedly analyze until a target score is reached.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "target_score": {"type": "integer", "default": 95},
                    "max_attempts": {"type": "integer", "default": 8},
                    "wait_between_attempts_sec": {"type": "integer", "default": 8},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="download_tailored_resume",
            description="Download the tailored resume as a PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "output_dir": {"type": "string"},
                    "resume_name": {"type": "string", "description": "Partial dashboard resume name"},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="get_resume_feedback",
            description="Get structured resume feedback from the ResumeUp Report tab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="apply_ai_fixes",
            description="Click ResumeUp Fix with AI buttons on the Report tab.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "max_fixes": {"type": "integer", "default": 5},
                    "trigger_analysis": {"type": "boolean", "default": True},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="improve_resume_until_target",
            description="Iteratively apply AI fixes and re-analyse until a target score is reached.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "target_score": {"type": "integer", "default": 95},
                    "max_rounds": {"type": "integer", "default": 5},
                    "max_fixes_per_round": {"type": "integer", "default": 5},
                    "wait_between_rounds_sec": {"type": "integer", "default": 8},
                    "job_description_text": {"type": "string"},
                },
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="tailor_and_download",
            description="One-shot ResumeUp pipeline: upload resume, tailor to job description, download PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_description_text": {"type": "string"},
                    "job_desc_file": {"type": "string"},
                    "session_id": {"type": "string"},
                    "email": {"type": "string"},
                    "password": {"type": "string"},
                    "headless": {"type": "boolean"},
                    "file_path": {"type": "string"},
                    "resume_id": {"type": "string"},
                    "resume_name": {"type": "string"},
                    "target_score": {"type": "integer", "default": 95},
                    "max_attempts": {"type": "integer", "default": 8},
                    "output_dir": {"type": "string"},
                    "close_session": {"type": "boolean", "default": False},
                },
            },
        ),
        types.Tool(
            name="end_browser_session",
            description="Close a browser session and release resources.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        ),
        types.Tool(
            name="linkedin_search_jobs",
            description="Search LinkedIn jobs and return listings (Easy Apply filter supported).",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "string"},
                    "location": {"type": "string"},
                    "easy_apply_only": {"type": "boolean", "default": True},
                    "remote_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 20},
                    "linkedin_email": {"type": "string"},
                    "linkedin_password": {"type": "string"},
                    "headless": {"type": "boolean"},
                    "close_linkedin_session": {"type": "boolean", "default": True},
                },
                "required": ["keywords"],
            },
        ),
        types.Tool(
            name="linkedin_get_job_details",
            description="Scrape full job description and metadata from a LinkedIn job URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_url": {"type": "string"},
                    "linkedin_email": {"type": "string"},
                    "linkedin_password": {"type": "string"},
                    "headless": {"type": "boolean"},
                    "close_linkedin_session": {"type": "boolean", "default": True},
                },
                "required": ["job_url"],
            },
        ),
        types.Tool(
            name="search_and_tailor",
            description="Search LinkedIn Easy Apply jobs, tailor resumes via ResumeUp, and populate the review queue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {"type": "string"},
                    "location": {"type": "string"},
                    "easy_apply_only": {"type": "boolean", "default": True},
                    "remote_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": DEFAULT_SEARCH_LIMIT},
                    "min_match_score": {"type": "number", "default": DEFAULT_MIN_MATCH_SCORE},
                    "daily_cap": {"type": "integer", "description": "Max jobs to tailor per day"},
                    "dedupe_company_title": {"type": "boolean", "default": True},
                    "profile_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Candidate skills for job matching (falls back to PROFILE_SKILLS env)",
                    },
                    "output_dir": {"type": "string"},
                    "session_id": {"type": "string", "description": "Existing ResumeUp session ID"},
                    "file_path": {"type": "string", "description": "Base resume file to upload"},
                    "resume_id": {"type": "string"},
                    "resume_name": {"type": "string"},
                    "target_score": {"type": "integer", "default": 95},
                    "max_attempts": {"type": "integer", "default": 8},
                    "linkedin_email": {"type": "string"},
                    "linkedin_password": {"type": "string"},
                    "headless": {"type": "boolean"},
                    "close_linkedin_session": {"type": "boolean", "default": True},
                },
                "required": ["keywords"],
            },
        ),
        types.Tool(
            name="get_application_history",
            description="List queued job applications (discovered, tailored, approved, applied, skipped, failed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        ),
        types.Tool(
            name="approve_application",
            description="Mark a tailored application as approved and ready for Easy Apply.",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string"},
                },
                "required": ["application_id"],
            },
        ),
        types.Tool(
            name="linkedin_easy_apply",
            description="Run LinkedIn Easy Apply for a queued application (assist mode by default).",
            inputSchema={
                "type": "object",
                "properties": {
                    "application_id": {"type": "string"},
                    "require_approval": {"type": "boolean", "default": True},
                    "submit": {"type": "boolean", "default": False},
                    "max_custom_questions": {"type": "integer", "default": 5},
                    "use_llm": {"type": "boolean", "description": "Use LLM for unmatched screening questions"},
                    "linkedin_email": {"type": "string"},
                    "linkedin_password": {"type": "string"},
                    "headless": {"type": "boolean"},
                    "close_linkedin_session": {"type": "boolean", "default": True},
                },
                "required": ["application_id"],
            },
        ),
        types.Tool(
            name="export_applications_csv",
            description="Export the application review queue to CSV.",
            inputSchema={
                "type": "object",
                "properties": {
                    "output_path": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="check_pipeline_setup",
            description="Validate env, profile, and tuning defaults before running the pipeline.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> types.CallToolResult:
    """Dispatch tool calls to synchronous Playwright handlers."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _error(f"Unknown tool: {name}")

    try:
        payload = await asyncio.to_thread(handler, arguments)
        return _tool_result(payload)
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return _error(f"Tool execution failed: {exc}")


async def main() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
