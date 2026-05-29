"""AI-assisted resume improvement orchestration."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from feedback_parser import format_feedback_for_prompt, parse_feedback_text
from models import ResumeFeedback

logger = logging.getLogger(__name__)

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent / "examples" / "prompinstructions.txt"


def load_prompt_instructions(path: Optional[str] = None) -> str:
    prompt_path = Path(path).expanduser() if path else DEFAULT_PROMPT_PATH
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt instructions not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def build_improvement_prompt(
    resume_text: str,
    job_description: str,
    feedback: ResumeFeedback,
    instructions_path: Optional[str] = None,
) -> str:
    template = load_prompt_instructions(instructions_path)
    feedback_text = format_feedback_for_prompt(feedback)
    return template.format(
        job_description=job_description.strip(),
        feedback=feedback_text,
        resume_text=resume_text.strip(),
    )


def improve_resume_until_target(
    handler,
    target_score: int = 95,
    max_rounds: int = 5,
    max_fixes_per_round: int = 5,
    wait_between_rounds_sec: int = 8,
    job_description: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the same improve loop used by the CLI, exposed for MCP tools."""
    logger.info("Starting AI improvement loop (target=%s)", target_score)

    final_score, attempts = handler.improve_until_target(
        target_score=target_score,
        max_attempts=max_rounds,
        wait_between_attempts=wait_between_rounds_sec,
    )
    feedback = handler.get_report_feedback()

    return {
        "success": final_score is not None,
        "target_reached": bool(final_score is not None and final_score >= target_score),
        "final_score": final_score,
        "rounds_completed": attempts,
        "fixes_applied": None,
        "feedback": feedback.to_dict(),
        "message": (
            f"Improvement complete. Final score: {final_score}"
            if final_score is not None
            else "Improvement finished without detecting a score"
        ),
    }


def load_feedback_from_file(path: str) -> ResumeFeedback:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    return parse_feedback_text(text)
