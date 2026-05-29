#!/usr/bin/env python3
"""Automate ResumeUp resume tailoring using a local resume and job description."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from constants import APP_URL, SESSION_DIR, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from resume_processor import ResumeProcessor
from resumeup_tools import ResumeUpHandler
from utils import (
    dismiss_editing_conflict,
    improve_until_target,
    is_signed_in,
    select_template_if_needed,
    wait_for_navigation,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate ResumeUp resume tailoring from a local resume and job description.",
    )
    parser.add_argument(
        "--resume-file",
        help="Local resume file to upload (PDF, DOCX, or TXT). Required unless --resume-id is given.",
    )
    parser.add_argument(
        "--job-desc-file",
        required=True,
        help="Local job description text file to upload or paste.",
    )
    parser.add_argument(
        "--score-target",
        type=int,
        default=95,
        help="Target ResumeUp score to reach before stopping.",
    )
    parser.add_argument(
        "--email",
        help="ResumeUp login email. If omitted, the script will reuse session or prompt for manual login.",
    )
    parser.add_argument(
        "--password",
        help="ResumeUp login password. Use with --email for automated sign in.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode when possible.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the actions the script would take without uploading files.",
    )
    parser.add_argument(
        "--session-dir",
        default=str(SESSION_DIR),
        help="Persistent browser session directory for ResumeUp login state.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for each ResumeUp action.",
    )
    parser.add_argument(
        "--resume-id",
        help="ResumeUp resume UUID to use instead of uploading a new file. "
        "Found in the editor URL: /resume-builder/{id}.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save the downloaded tailored resume PDF. Defaults to current directory.",
    )
    return parser.parse_args()


def run_automation(args: argparse.Namespace) -> int:
    if not args.resume_id and not args.resume_file:
        logger.error("Provide --resume-file (upload new) or --resume-id (use existing).")
        return 1

    resume_file: Optional[Path] = None
    if args.resume_file:
        resume_file = Path(args.resume_file).expanduser().resolve()
        if not resume_file.exists():
            logger.error("Resume file not found: %s", resume_file)
            return 1

    job_desc_file = Path(args.job_desc_file).expanduser().resolve()
    if not job_desc_file.exists():
        logger.error("Job description file not found: %s", job_desc_file)
        return 1

    if args.dry_run:
        logger.info("Running in dry-run mode. No files will be uploaded.")

    session_dir = Path(args.session_dir).expanduser()
    session_dir.mkdir(parents=True, exist_ok=True)

    email = args.email or os.environ.get("RESUMEUP_EMAIL")
    password = args.password or os.environ.get("RESUMEUP_PASSWORD")

    with sync_playwright() as playwright:
        has_session = (session_dir / "Default" / "Cookies").exists()
        browser_context = playwright.chromium.launch_persistent_context(
            str(session_dir),
            headless=args.headless if (email and password) or has_session else False,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )
        page = browser_context.new_page()
        handler = ResumeUpHandler(page, timeout=args.timeout)
        processor = ResumeProcessor(session_dir=session_dir, timeout=args.timeout)
        processor.page = page
        processor.browser_context = browser_context

        page.goto(APP_URL, timeout=args.timeout * 1000)
        wait_for_navigation(page, args.timeout)

        if not is_signed_in(page):
            if email and password:
                if not processor.sign_in(email, password):
                    logger.error("Automated sign-in failed")
                    browser_context.close()
                    return 1
            elif not processor.manual_login():
                logger.error("Manual login failed")
                browser_context.close()
                return 1

        if args.resume_id:
            logger.info("Using existing resume ID: %s", args.resume_id)
            if not processor.navigate_to_editor(args.resume_id):
                browser_context.close()
                return 1
            dismiss_editing_conflict(page)
        else:
            if args.dry_run:
                logger.info("DRY RUN: would upload resume %s", resume_file)
                logger.info("DRY RUN: would upload job description %s", job_desc_file)
            else:
                if handler.upload_resume(resume_file) is None:
                    browser_context.close()
                    return 1
                handler.upload_job_description_file(job_desc_file)
                select_template_if_needed(page, args.timeout)
                dismiss_editing_conflict(page)

        try:
            final_score, _attempts = improve_until_target(
                page,
                target_score=args.score_target,
                dry_run=args.dry_run,
                timeout=args.timeout,
            )
        except RuntimeError as exc:
            logger.error("%s", exc)
            browser_context.close()
            return 2

        screenshot_path = Path.cwd() / "resumeup_tailor_result.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info("Saved final page screenshot to %s", screenshot_path)

        if not args.dry_run:
            output_dir = Path(args.output_dir).expanduser().resolve()
            downloaded = handler.download_resume(output_dir)
            if not downloaded:
                logger.warning(
                    "Automatic download failed. Open the ResumeUp dashboard and download "
                    "manually via the '...' menu → Download."
                )

        browser_context.close()

    return 0 if final_score >= args.score_target else 2


def main() -> int:
    args = parse_args()
    if not args.headless and not args.email and not args.password:
        logger.info("No email/password provided. The browser will open for manual login.")
    return run_automation(args)


if __name__ == "__main__":
    raise SystemExit(main())
