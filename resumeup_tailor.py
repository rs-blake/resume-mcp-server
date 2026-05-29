#!/usr/bin/env python3
"""CLI for tailoring a resume on ResumeUp.ai (original automation workflow)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from job_parser import parse_job_description
from resume_processor import ResumeProcessor
from session_manager import create_session, end_session

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_path(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def run_tailoring(args: argparse.Namespace) -> int:
    """Execute the full upload -> tailor -> score -> download workflow."""
    resume_path = _resolve_path(args.resume) if args.resume else None
    job_text = Path(os.path.expanduser(args.job_desc)).read_text(encoding="utf-8")
    output_dir = _resolve_path(args.output_dir)

    email = args.email or os.getenv("RESUMEUP_EMAIL")
    password = args.password or os.getenv("RESUMEUP_PASSWORD")
    headless = args.headless or os.getenv("RESUMEUP_HEADLESS", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    parsed_job = parse_job_description(job_text)
    logger.info("Target job: %s (%s)", parsed_job.title, parsed_job.company or "unknown company")

    processor = ResumeProcessor()
    session = create_session(processor, headless=headless)
    session_id = session.session_id

    try:
        if not processor.ensure_logged_in(email, password):
            logger.error("Authentication failed")
            return 1

        handler = session.handler

        if resume_path:
            resume_data = handler.upload_resume(resume_path)
            if resume_data is None:
                logger.error("Resume upload failed")
                return 1

            session.resume_data = resume_data
            session.resume_id = resume_data.id

            if not processor.select_template():
                logger.warning("Template selection step skipped or failed")

        elif args.resume_name:
            logger.info("Using existing dashboard resume: %s", args.resume_name)
        else:
            logger.info("No resume file provided; using the first dashboard resume")

        if not handler.enter_job_description(job_text, resume_name=args.resume_name):
            logger.error("Failed to enter job description")
            return 1

        if args.skip_poll:
            score = handler.get_score()
            logger.info("Current score: %s", score if score is not None else "unknown")
        else:
            final_score, attempts = handler.poll_score_until_target(
                target_score=args.target_score,
                max_attempts=args.max_attempts,
                wait_between_attempts=args.wait_seconds,
            )
            logger.info(
                "Final score: %s after %s attempt(s) (target: %s)",
                final_score,
                attempts,
                args.target_score,
            )

        if args.no_download:
            logger.info("Skipping download (--no-download)")
            return 0

        downloaded = handler.download_resume(output_dir, resume_name=args.resume_name)
        if downloaded is None:
            logger.error("Download failed")
            return 1

        logger.info("Saved tailored resume to %s", downloaded)
        return 0
    finally:
        if not args.keep_session:
            end_session(session_id)
        else:
            logger.info("Session kept open: %s", session_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tailor a resume on ResumeUp.ai using Playwright automation.",
    )
    parser.add_argument(
        "--resume",
        help="Path to a local resume file (PDF/DOCX). Omit to tailor an existing dashboard resume.",
    )
    parser.add_argument(
        "--resume-name",
        help="Partial name of an existing dashboard resume (e.g. resume_stock).",
    )
    parser.add_argument(
        "--job-desc",
        default="jobDesc.txt",
        help="Path to job description text file (default: jobDesc.txt)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for downloaded PDF (default: current directory)",
    )
    parser.add_argument("--email", help="ResumeUp email (or RESUMEUP_EMAIL env var)")
    parser.add_argument("--password", help="ResumeUp password (or RESUMEUP_PASSWORD env var)")
    parser.add_argument("--target-score", type=int, default=95, help="Target resume score")
    parser.add_argument("--max-attempts", type=int, default=8, help="Max re-analysis attempts")
    parser.add_argument("--wait-seconds", type=int, default=8, help="Wait between score checks")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--skip-poll", action="store_true", help="Skip score polling loop")
    parser.add_argument("--no-download", action="store_true", help="Skip PDF download")
    parser.add_argument(
        "--keep-session",
        action="store_true",
        help="Leave browser session open after completion",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not Path(os.path.expanduser(args.job_desc)).exists():
        parser.error(f"Job description file not found: {args.job_desc}")

    if args.resume and not _resolve_path(args.resume).exists():
        parser.error(f"Resume file not found: {args.resume}")

    sys.exit(run_tailoring(args))


if __name__ == "__main__":
    main()
