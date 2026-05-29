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
from resume_processor import ResumeProcessor
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


TOOL_HANDLERS = {
    "start_browser_session": _handle_start_browser_session,
    "upload_resume": _handle_upload_resume,
    "parse_job_description": _handle_parse_job_description,
    "upload_job_to_resumeup": _handle_upload_job_to_resumeup,
    "get_resume_score": _handle_get_resume_score,
    "trigger_analysis": _handle_trigger_analysis,
    "poll_score_until_target": _handle_poll_score_until_target,
    "download_tailored_resume": _handle_download_tailored_resume,
    "end_browser_session": _handle_end_browser_session,
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
            name="end_browser_session",
            description="Close a browser session and release resources.",
            inputSchema={
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
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
