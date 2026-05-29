"""Common utility functions for Playwright automation."""

import logging
import re
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from constants import BUTTON_PATTERNS, SCORE_PATTERNS

logger = logging.getLogger(__name__)

RESUME_BUILDER_PATH = re.compile(r"/resume-builder/([0-9a-f-]{36})", re.I)


def wait_for_navigation(page, timeout: int = 120) -> None:
    """Wait for page load and network idle."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
        page.wait_for_load_state("networkidle", timeout=min(timeout, 30) * 1000)
    except Exception:
        page.wait_for_timeout(1000)


def is_signed_in(page) -> bool:
    """Return True when the current page indicates an authenticated session."""
    url = (page.url or "").lower()
    if "signin" in url or "login" in url:
        return False

    try:
        body = page.inner_text("body").lower()
    except Exception:
        return False

    sign_out_markers = ("sign out", "signout", "log out", "logout")
    return any(marker in body for marker in sign_out_markers)


def click_button_by_patterns(page, patterns: Iterable[str], timeout: int = 120) -> bool:
    """Click the first visible button matching any regex pattern."""
    for pattern in patterns:
        locator = page.locator(
            "button:visible:not([disabled]), a:visible",
            has_text=re.compile(pattern, re.I),
        )
        if locator.count() == 0:
            continue

        try:
            locator.first.click(timeout=timeout * 1000)
            return True
        except Exception as exc:
            logger.debug("Button click failed for pattern %s: %s", pattern, exc)

    return False


def set_input_files(page, file_path: Path) -> bool:
    """Set files on the first available file input."""
    file_input = page.locator('input[type="file"]')
    if file_input.count() == 0:
        return False

    try:
        file_input.first.set_input_files(str(file_path))
        return True
    except Exception as exc:
        logger.error("Failed to set input files: %s", exc)
        return False


def extract_resume_id_from_url(url: str) -> Optional[str]:
    """Extract resume UUID from a ResumeUp editor URL."""
    match = RESUME_BUILDER_PATH.search(url or "")
    return match.group(1) if match else None


def navigate_to_report_tab(page, timeout: int = 120) -> bool:
    """Navigate to the Report tab in the resume editor."""
    dismiss_editing_conflict(page)

    report_tab = page.locator(
        "button:visible, a:visible",
        has_text=re.compile(r"^Report$", re.I),
    )
    if report_tab.count() == 0:
        report_tab = page.locator("button, a", has_text=re.compile(r"report", re.I))

    if report_tab.count() == 0:
        return False

    try:
        report_tab.first.click(timeout=timeout * 1000)
        page.wait_for_timeout(1500)
        return True
    except Exception as exc:
        logger.error("Failed to open Report tab: %s", exc)
        return False


def find_resume_score(page) -> Optional[int]:
    """Extract resume score from the current page text."""
    try:
        text = page.inner_text("body")
    except Exception:
        return None

    scores = []
    for pattern in SCORE_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            score = int(match.group(1))
            if 0 <= score <= 100:
                scores.append(score)

    if not scores:
        return None

    # Prefer the largest score-like value in report contexts (e.g. 79/100).
    return max(scores)


def dismiss_editing_conflict(page) -> bool:
    """Dismiss ResumeUp editing conflict dialogs when present."""
    heading = page.locator("text=/editing conflict detected/i")
    if heading.count() == 0:
        return False

    if click_button_by_patterns(page, BUTTON_PATTERNS["continue_editing"], timeout=10):
        page.wait_for_timeout(1000)
        return True

    fallback_patterns = [
        r"use\s+this\s+version",
        r"ok",
        r"close",
    ]
    return click_button_by_patterns(page, fallback_patterns, timeout=10)


def fill_job_description_textarea(page, job_text: str) -> bool:
    """Fill the first visible job-description textarea on the page."""
    textareas = page.locator("textarea:visible")
    for idx in range(textareas.count()):
        area = textareas.nth(idx)
        placeholder = (area.get_attribute("placeholder") or "").lower()
        aria = (area.get_attribute("aria-label") or "").lower()
        label_text = (area.get_attribute("name") or "").lower()

        if any(
            token in placeholder or token in aria or token in label_text
            for token in ("job", "description", "jd", "posting")
        ):
            area.click()
            area.fill(job_text)
            return True

    if textareas.count() > 0:
        textareas.first.click()
        textareas.first.fill(job_text)
        return True

    return False
