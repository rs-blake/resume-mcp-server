"""Common utility functions for Playwright automation."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional

from constants import BUTTON_PATTERNS, SCORE_PATTERNS, TEMPLATE_PATTERNS

logger = logging.getLogger(__name__)

RESUME_BUILDER_PATH = re.compile(r"/resume-builder/([0-9a-f-]{36})", re.I)


def wait_for_navigation(page, timeout: int = 120) -> None:
    """Wait for page load and network idle."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
        except Exception:
            pass
    page.wait_for_timeout(1000)


def is_signed_in(page) -> bool:
    """Return True when the current page indicates an authenticated session."""
    if "signin" in (page.url or "").lower():
        return False
    if page.locator("#email-signin").count() > 0:
        return False
    return True


def click_button_by_patterns(page, patterns: Iterable[str], timeout: int = 15) -> bool:
    """Click the first visible, enabled button or link matching any pattern."""
    for pattern in patterns:
        compiled = re.compile(pattern, re.I)
        for selector in ["button:visible:not([disabled])", "a:visible:not([disabled])"]:
            locator = page.locator(selector, has_text=compiled)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=timeout * 1000)
                return True
            except Exception as exc:
                logger.debug("Button click failed for %s: %s", pattern, exc)
    return False


def set_input_files(page, file_path: Path) -> bool:
    """Set files on the first available file input."""
    file_inputs = page.locator('input[type="file"]')
    if file_inputs.count() == 0:
        return False
    try:
        file_inputs.first.set_input_files(str(file_path))
        return True
    except Exception as exc:
        logger.error("Failed to set input files: %s", exc)
        return False


def extract_resume_id_from_url(url: str) -> Optional[str]:
    """Extract resume UUID from a ResumeUp editor URL."""
    match = RESUME_BUILDER_PATH.search(url or "")
    return match.group(1) if match else None


def dismiss_editing_conflict(page) -> bool:
    """Dismiss the ResumeUp editing conflict overlay if present."""
    portal = page.locator("#headlessui-portal-root")
    if portal.count() == 0:
        return False

    try:
        portal_text = portal.first.inner_text()
    except Exception:
        return False

    if "Editing Conflict" not in portal_text:
        return False

    btn = page.locator("button:visible", has_text="Continue Editing Here")
    if btn.count():
        btn.first.click()
    else:
        portal.locator("button").nth(1).click()

    page.wait_for_timeout(1200)
    logger.info("Dismissed editing conflict overlay")
    return True


def navigate_to_report_tab(page, timeout: int = 30) -> bool:
    """Open the Report tab and wait for score/analysis controls."""
    report_tab = page.locator(
        "button:visible:not([disabled])",
        has_text=re.compile(r"^Report$", re.I),
    )
    if report_tab.count():
        try:
            report_tab.first.click(timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

    content_pattern = re.compile(r"re-analy|analyze.my.resume|resume.score", re.I)
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = page.inner_text("body")
        if content_pattern.search(body):
            return True
        time.sleep(1)
    return False


def find_resume_score(page) -> Optional[int]:
    """Extract resume score from the current page text."""
    try:
        text = page.inner_text("body").replace("\n", " ")
    except Exception:
        return None

    for pattern in SCORE_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            score = int(match.group(1))
            if 0 <= score <= 100:
                return score

    fallback = re.findall(r"\b(\d{2,3})\b", text)
    for candidate in reversed(fallback[-8:]):
        score_value = int(candidate)
        if 50 <= score_value <= 100:
            return score_value
    return None


def handle_ai_dialog(page) -> int:
    """Wait for AI suggestion dialog, click Apply buttons, and close dialog."""
    dialog_deadline = time.time() + 6
    while time.time() < dialog_deadline:
        portal = page.locator("#headlessui-portal-root")
        if portal.count():
            try:
                portal_text = portal.first.inner_text()
                if re.search(r"add.with.ai|fix.with.ai", portal_text, re.I):
                    break
            except Exception:
                pass
        time.sleep(1)
    else:
        logger.debug("No AI dialog appeared (direct-action button); skipping")
        return 0

    deadline = time.time() + 30
    while time.time() < deadline:
        portal = page.locator("#headlessui-portal-root")
        if portal.count() == 0:
            time.sleep(1)
            continue
        try:
            portal_text = portal.first.inner_text()
        except Exception:
            time.sleep(1)
            continue
        if not re.search(r"add.with.ai|fix.with.ai", portal_text, re.I):
            time.sleep(1)
            continue

        btn_texts: List[str] = page.evaluate(
            """() => {
            const p = document.querySelector('#headlessui-portal-root');
            if (!p) return [];
            return [...p.querySelectorAll('button')].map(b => b.textContent.trim());
        }"""
        )
        if any(re.search(r"^apply$", text, re.I) for text in btn_texts):
            logger.debug("AI dialog Apply buttons loaded: %s", btn_texts)
            break
        logger.debug("AI dialog open, Apply not yet loaded (buttons=%s)", btn_texts)
        time.sleep(2)
    else:
        logger.warning("Timed out waiting for AI dialog Apply buttons")
        return 0

    clicks = 0
    for _ in range(20):
        result: Optional[str] = page.evaluate(
            """() => {
            const p = document.querySelector('#headlessui-portal-root');
            if (!p) return null;
            const btn = [...p.querySelectorAll('button')]
                .find(b => /^\\s*apply\\s*$/i.test(b.textContent.trim()) && !b.disabled);
            if (btn) { btn.click(); return btn.textContent.trim(); }
            return null;
        }"""
        )
        if result:
            clicks += 1
            page.wait_for_timeout(1500)
        else:
            break

    closed: bool = page.evaluate(
        """() => {
        const p = document.querySelector('#headlessui-portal-root');
        if (!p) return false;
        for (const aria of ['Close', 'close', 'Dismiss', 'dismiss']) {
            const b = p.querySelector(`button[aria-label="${aria}"]`);
            if (b) { b.click(); return true; }
        }
        const xBtn = [...p.querySelectorAll('button')]
            .find(b => /^[\\u00d7xX]$/.test(b.textContent.trim()));
        if (xBtn) { xBtn.click(); return true; }
        return false;
    }"""
    )
    if not closed:
        page.keyboard.press("Escape")
    page.wait_for_timeout(800)
    return clicks


def apply_ai_suggestions(page, max_per_round: int = 5) -> int:
    """Click Fix with AI / Add with AI buttons and apply dialog suggestions."""
    pattern = re.compile(r"fix.with.ai|add.with.ai|add.all.to.skills", re.I)
    applied = 0

    for _ in range(max_per_round):
        locator = page.locator("button:visible:not([disabled])", has_text=pattern)
        if locator.count() == 0:
            break
        try:
            locator.first.click(timeout=8000)
            handle_ai_dialog(page)
            page.wait_for_timeout(1000)
            applied += 1
        except Exception as exc:
            logger.warning("AI suggestion click failed: %s", exc)
            break

    return applied


def wait_and_click_reanalyse(page, max_wait: int = 45) -> bool:
    """Wait for Re-analyse to become enabled, then click it."""
    pattern = re.compile(r"re-analy", re.I)
    deadline = time.time() + max_wait

    while time.time() < deadline:
        for selector in [
            "button:visible:not([disabled]):not([aria-disabled='true'])",
            "button:visible:not([disabled])",
        ]:
            locator = page.locator(selector, has_text=pattern)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=5000)
                logger.info("Re-analyse button clicked")
                return True
            except Exception as exc:
                logger.debug("Re-analyse click retry: %s", exc)
        time.sleep(2)

    try:
        result = page.evaluate(
            """() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => /re-analy/i.test(b.textContent));
                if (btn) { btn.click(); return btn.textContent.trim(); }
                return null;
            }"""
        )
        if result:
            logger.info("Re-analyse clicked via JS")
            return True
    except Exception as exc:
        logger.warning("Re-analyse JS fallback failed: %s", exc)

    return False


def fill_job_description_textarea(page, job_text: str) -> bool:
    """Fill the job description textarea in the Report tab."""
    textareas = page.locator("textarea:visible")
    for idx in range(textareas.count()):
        area = textareas.nth(idx)
        placeholder = (area.get_attribute("placeholder") or "").lower()
        aria = (area.get_attribute("aria-label") or "").lower()
        if any(token in placeholder or token in aria for token in ("job", "description", "jd")):
            area.triple_click()
            area.fill(job_text)
            return True

    if textareas.count() > 0:
        textareas.first.triple_click()
        textareas.first.fill(job_text)
        return True

    return False


def select_template_if_needed(page, timeout: int = 120) -> bool:
    """Select a template when the picker step is shown."""
    try:
        body = page.inner_text("body", timeout=5000)
    except Exception:
        body = ""

    if "TEMPLATES" not in body.upper() and "/resume-builder/" in page.url:
        return True

    logger.info("Selecting resume template")
    if click_button_by_patterns(page, TEMPLATE_PATTERNS, timeout=min(timeout, 15)):
        try:
            page.wait_for_url("**/resume-builder/**", timeout=timeout * 1000)
            wait_for_navigation(page, timeout)
            return True
        except Exception as exc:
            logger.warning("Template selection navigation failed: %s", exc)
            return False
    return False

def improve_until_target(
    page,
    target_score: int,
    dry_run: bool = False,
    timeout: int = 120,
    max_attempts: int = 8,
) -> tuple[Optional[int], int]:
    """Run the score improvement loop from the latest resumeup_tailor.py script."""
    if dry_run:
        logger.info("DRY RUN: would poll score until %s", target_score)
        return 0, 0

    logger.info("Starting score evaluation loop...")
    best_score = None
    attempts = 0

    while attempts < max_attempts:
        attempts += 1
        dismiss_editing_conflict(page)
        navigate_to_report_tab(page, min(timeout, 60))
        wait_for_navigation(page, timeout)

        score = find_resume_score(page)
        if score is not None:
            best_score = score
            logger.info("Found resume score: %s", score)
            if score >= target_score:
                logger.info("Target score %s reached", target_score)
                return score, attempts
        else:
            logger.warning("Unable to detect the current score yet")

        analyze_my = page.locator(
            "button:visible:not([disabled])",
            has_text=re.compile(r"analyze.my.resume", re.I),
        )
        if analyze_my.count():
            logger.info("Clicking Analyze My Resume")
            analyze_my.first.click(timeout=10000)
            time.sleep(10)
            continue

        applied = apply_ai_suggestions(page, max_per_round=5)
        if applied > 0:
            logger.info("Applied %s AI suggestion(s); returning to Report tab", applied)
            navigate_to_report_tab(page, 30)
            time.sleep(2)

        clicked = wait_and_click_reanalyse(page, max_wait=45)
        if not clicked:
            if applied == 0:
                logger.warning("No AI suggestions or analyze button available; ending loop")
                break
            logger.warning("Re-analyse not clickable after suggestions; retrying next round")
        else:
            time.sleep(12)

        if score is not None and score >= target_score:
            return score, attempts

    if best_score is not None:
        logger.info("Stopped after %s attempts; best score was %s", attempts, best_score)
        return best_score, attempts

    raise RuntimeError("Could not complete score review or detect the resume score")

