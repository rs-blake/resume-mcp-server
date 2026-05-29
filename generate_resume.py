#!/usr/bin/env python3
"""Build LLM prompts and apply external resume rewrites to ResumeUp."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from feedback_parser import format_feedback_for_prompt, parse_feedback_text
from models import ResumeFeedback
from resume_processor import ResumeProcessor
from resume_sections import parse_resume_sections
from session_manager import create_session, end_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
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


def load_feedback_from_file(path: str) -> ResumeFeedback:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    return parse_feedback_text(text)


def improve_resume_until_target(
    handler,
    target_score: int = 95,
    max_rounds: int = 5,
    max_fixes_per_round: int = 5,
    wait_between_rounds_sec: int = 8,
    job_description: Optional[str] = None,
) -> Dict[str, Any]:
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


def cmd_build_prompt(args: argparse.Namespace) -> int:
    job_text = Path(args.job_desc_file).expanduser().read_text(encoding="utf-8")
    resume_text = Path(args.resume_file).expanduser().read_text(encoding="utf-8")
    feedback = (
        load_feedback_from_file(args.feedback_file)
        if args.feedback_file
        else parse_feedback_text(args.feedback or "")
    )

    prompt = build_improvement_prompt(
        resume_text=resume_text,
        job_description=job_text,
        feedback=feedback,
        instructions_path=args.prompt_instructions_file,
    )

    output = Path(args.output).expanduser()
    output.write_text(prompt, encoding="utf-8")
    logger.info("Wrote improvement prompt to %s", output)
    return 0


def cmd_parse_feedback(args: argparse.Namespace) -> int:
    feedback = load_feedback_from_file(args.feedback_file)
    payload = feedback.to_dict()
    text = json.dumps(payload, indent=2)

    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        logger.info("Wrote parsed feedback to %s", args.output)
    else:
        print(text)
    return 0


def cmd_parse_resume(args: argparse.Namespace) -> int:
    text = Path(args.resume_file).expanduser().read_text(encoding="utf-8")
    sections = parse_resume_sections(text)
    payload = json.dumps(sections, indent=2)

    if args.output:
        Path(args.output).expanduser().write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


def cmd_apply_updated(args: argparse.Namespace) -> int:
    updated_text = Path(args.updated_file).expanduser().read_text(encoding="utf-8")

    processor = ResumeProcessor()
    session = create_session(processor, headless=args.headless)
    try:
        if not processor.ensure_logged_in(args.email, args.password):
            logger.error("Authentication failed")
            return 1

        if args.resume_id and not processor.navigate_to_editor(args.resume_id):
            logger.error("Could not open resume editor")
            return 1

        results = session.handler.apply_resume_text(updated_text)
        logger.info("Applied sections: %s", results)

        if args.reanalyse:
            session.handler.trigger_analysis()

        if args.target_score:
            final = improve_resume_until_target(
                session.handler,
                target_score=args.target_score,
                max_rounds=args.max_rounds,
            )
            logger.info("Post-apply improvement result: %s", final)

        return 0
    finally:
        if not args.keep_session:
            end_session(session.session_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate ResumeUp improvement prompts and apply external LLM rewrites.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-prompt", help="Build an LLM improvement prompt file")
    build.add_argument("--job-desc-file", required=True)
    build.add_argument("--resume-file", required=True, help="Current resume text file")
    build.add_argument("--feedback-file", help="resumefeedback.txt path")
    build.add_argument("--feedback", default="", help="Inline feedback text")
    build.add_argument("--prompt-instructions-file", default="examples/prompinstructions.txt")
    build.add_argument("--output", default="prompt.txt")
    build.set_defaults(func=cmd_build_prompt)

    parse_fb = sub.add_parser("parse-feedback", help="Parse feedback file to JSON")
    parse_fb.add_argument("--feedback-file", required=True)
    parse_fb.add_argument("--output")
    parse_fb.set_defaults(func=cmd_parse_feedback)

    parse_res = sub.add_parser("parse-resume", help="Parse updated resume sections to JSON")
    parse_res.add_argument("--resume-file", required=True)
    parse_res.add_argument("--output")
    parse_res.set_defaults(func=cmd_parse_resume)

    apply = sub.add_parser("apply-updated", help="Apply resume_updated.txt to ResumeUp editor")
    apply.add_argument("--updated-file", default="resume_updated.txt")
    apply.add_argument("--resume-id", help="ResumeUp resume UUID")
    apply.add_argument("--email")
    apply.add_argument("--password")
    apply.add_argument("--headless", action="store_true")
    apply.add_argument("--reanalyse", action="store_true", help="Trigger analysis after apply")
    apply.add_argument("--target-score", type=int, help="Run improve loop after apply")
    apply.add_argument("--max-rounds", type=int, default=5)
    apply.add_argument("--keep-session", action="store_true")
    apply.set_defaults(func=cmd_apply_updated)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
