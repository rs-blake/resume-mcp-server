"""LinkedIn Easy Apply automation (assist mode with optional submit)."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from linkedin_processor import LinkedInProcessor

logger = logging.getLogger(__name__)

EASY_APPLY_BUTTON = re.compile(r"Easy Apply", re.I)
NEXT_BUTTON = re.compile(r"^(Next|Review|Continue)$", re.I)
SUBMIT_BUTTON = re.compile(r"^(Submit application|Submit)$", re.I)
DISCARD_BUTTON = re.compile(r"Discard", re.I)


def _click_easy_apply(page) -> bool:
    for locator in [
        page.locator("button.jobs-apply-button").filter(has_text=EASY_APPLY_BUTTON),
        page.get_by_role("button", name=EASY_APPLY_BUTTON),
    ]:
        if locator.count() > 0:
            try:
                locator.first.click(timeout=5000)
                time.sleep(1.5)
                return True
            except Exception:
                continue
    return False


def _upload_resume_if_needed(page, resume_path: Path) -> bool:
    file_inputs = page.locator('input[type="file"]')
    if file_inputs.count() == 0:
        return True

    try:
        file_inputs.first.set_input_files(str(resume_path))
        time.sleep(1)
        return True
    except Exception as exc:
        logger.error("Failed to upload resume: %s", exc)
        return False


def _answer_simple_questions(page, profile: Dict[str, str]) -> int:
    """Fill common screening fields using profile defaults."""
    answered = 0

    for key, value in profile.items():
        if not value:
            continue

        label_patterns = [
            re.compile(re.escape(key), re.I),
            re.compile(key.replace("_", " "), re.I),
        ]
        for pattern in label_patterns:
            field = page.get_by_label(pattern)
            if field.count() > 0:
                try:
                    field.first.fill(value)
                    answered += 1
                except Exception:
                    pass

    # Common radio/select patterns
    for pattern, answer in [
        (r"authorized to work", profile.get("work_authorization", "Yes")),
        (r"sponsorship", profile.get("requires_sponsorship", "No")),
        (r"years of work experience", profile.get("years_experience", "")),
    ]:
        if not answer:
            continue
        option = page.get_by_role("radio", name=re.compile(answer, re.I))
        if option.count() > 0:
            try:
                option.first.click(timeout=2000)
                answered += 1
            except Exception:
                pass

    return answered


def _count_custom_questions(page) -> int:
    return (
        page.locator("fieldset").count()
        + page.locator('div[data-test-form-element]').count()
        + page.locator("textarea").count()
    )


def _advance_steps(
    page,
    resume_path: Optional[Path],
    profile: Dict[str, str],
    max_steps: int = 10,
) -> Dict[str, Any]:
    """Walk through Easy Apply wizard steps."""
    steps_completed = 0
    questions_seen = 0

    for _ in range(max_steps):
        questions_seen = max(questions_seen, _count_custom_questions(page))

        if resume_path:
            _upload_resume_if_needed(page, resume_path)

        _answer_simple_questions(page, profile)

        submit = page.get_by_role("button", name=SUBMIT_BUTTON)
        if submit.count() > 0:
            return {
                "ready_to_submit": True,
                "steps_completed": steps_completed,
                "custom_questions": questions_seen,
            }

        next_button = page.get_by_role("button", name=NEXT_BUTTON)
        review_button = page.get_by_role("button", name=re.compile(r"Review", re.I))
        target = next_button if next_button.count() > 0 else review_button

        if target.count() == 0:
            break

        try:
            target.first.click(timeout=5000)
            steps_completed += 1
            time.sleep(1.5)
        except Exception:
            break

    return {
        "ready_to_submit": False,
        "steps_completed": steps_completed,
        "custom_questions": questions_seen,
    }


def _close_modal(page) -> None:
    for pattern in [DISCARD_BUTTON, re.compile(r"Close", re.I)]:
        button = page.get_by_role("button", name=pattern)
        if button.count() > 0:
            try:
                button.first.click(timeout=3000)
                return
            except Exception:
                continue


def run_easy_apply(
    processor: LinkedInProcessor,
    job_url: str,
    resume_path: Optional[str] = None,
    profile: Optional[Dict[str, str]] = None,
    require_approval: bool = True,
    max_custom_questions: int = 3,
    submit: bool = False,
) -> Dict[str, Any]:
    """Open Easy Apply for a job and optionally submit the application."""
    assert processor.page is not None
    page = processor.page
    profile = profile or {}

    page.goto(job_url.split("?")[0], timeout=processor.timeout * 1000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    if not _click_easy_apply(page):
        return {
            "success": False,
            "message": "Easy Apply button not found on this job",
            "submitted": False,
        }

    resume = Path(resume_path).expanduser() if resume_path else None
    if resume and not resume.exists():
        return {
            "success": False,
            "message": f"Resume file not found: {resume}",
            "submitted": False,
        }

    progress = _advance_steps(page, resume, profile)
    custom_questions = progress["custom_questions"]

    if custom_questions > max_custom_questions:
        _close_modal(page)
        return {
            "success": False,
            "submitted": False,
            "custom_questions": custom_questions,
            "message": (
                f"Skipped: job has {custom_questions} custom questions "
                f"(max allowed: {max_custom_questions})"
            ),
        }

    if not progress["ready_to_submit"]:
        _close_modal(page)
        return {
            "success": False,
            "submitted": False,
            "custom_questions": custom_questions,
            "steps_completed": progress["steps_completed"],
            "message": "Could not reach the submit step — manual review required",
        }

    if require_approval and not submit:
        return {
            "success": True,
            "submitted": False,
            "ready_to_submit": True,
            "custom_questions": custom_questions,
            "message": "Application pre-filled and ready for your review before submit",
        }

    submit_button = page.get_by_role("button", name=SUBMIT_BUTTON)
    if submit_button.count() == 0:
        _close_modal(page)
        return {
            "success": False,
            "submitted": False,
            "message": "Submit button not found",
        }

    try:
        submit_button.first.click(timeout=5000)
        time.sleep(2)
        return {
            "success": True,
            "submitted": True,
            "custom_questions": custom_questions,
            "message": "Application submitted via Easy Apply",
        }
    except Exception as exc:
        _close_modal(page)
        return {
            "success": False,
            "submitted": False,
            "message": f"Submit failed: {exc}",
        }
