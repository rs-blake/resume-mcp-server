"""ResumeUp.ai browser automation handlers."""

from __future__ import annotations

import re
import time
import logging
from typing import Optional
from pathlib import Path

from models import ResumeData, ResumeFeedback
from feedback_parser import parse_feedback_text
from utils import (
    apply_ai_suggestions,
    click_button_by_patterns,
    dismiss_editing_conflict,
    extract_resume_id_from_url,
    fill_job_description_textarea,
    find_resume_score,
    navigate_to_report_tab,
    set_input_files,
    wait_and_click_reanalyse,
    wait_for_navigation,
)
from constants import APP_URL, BUTTON_PATTERNS, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)


class ResumeUpHandler:
    """Handles Playwright interactions with ResumeUp.ai"""

    def __init__(self, page, timeout: int = DEFAULT_TIMEOUT):
        self.page = page
        self.timeout = timeout

    def _open_dashboard(self) -> None:
        self.page.goto(APP_URL, timeout=self.timeout * 1000)
        wait_for_navigation(self.page, self.timeout)
        dismiss_editing_conflict(self.page)

    def _wait_for_editor(self) -> bool:
        try:
            self.page.wait_for_url("**/resume-builder/**", timeout=self.timeout * 1000)
            wait_for_navigation(self.page, self.timeout)
            dismiss_editing_conflict(self.page)
            return True
        except Exception as exc:
            logger.error("Editor did not load: %s", exc)
            return False

    def _open_resume_card_menu(self, resume_name: Optional[str] = None) -> bool:
        if resume_name:
            card = self.page.locator(
                "div, article, li",
                has_text=re.compile(re.escape(resume_name), re.I),
            )
            if card.count():
                menu = card.first.locator("button").filter(has_text=re.compile(r"^\.\.\.$|^…$"))
                if menu.count():
                    menu.first.click()
                    self.page.wait_for_timeout(800)
                    return True

        dots = self.page.locator("button:visible").filter(
            has_text=re.compile(r"^\.\.\.$|^…$")
        )
        if dots.count() == 0:
            return False

        dots.first.click()
        self.page.wait_for_timeout(800)
        return True

    def upload_resume(self, file_path: Path) -> Optional[ResumeData]:
        logger.info("Uploading resume: %s", file_path)
        if not file_path.exists():
            logger.error("Resume file not found: %s", file_path)
            return None

        self._open_dashboard()
        uploaded = False
        if click_button_by_patterns(self.page, BUTTON_PATTERNS["resume_upload"], self.timeout):
            wait_for_navigation(self.page, self.timeout)
            uploaded = set_input_files(self.page, file_path)
        if not uploaded:
            uploaded = set_input_files(self.page, file_path)
        if not uploaded:
            logger.error("Could not find file upload control for resume")
            return None

        time.sleep(2)
        self._wait_for_editor()
        resume_id = extract_resume_id_from_url(self.page.url) or str(int(time.time()))

        try:
            text = self.page.inner_text("body")
            preview = text[:500] if text else ""
        except Exception as exc:
            logger.error("Error extracting resume data: %s", exc)
            return None

        return ResumeData(
            id=resume_id,
            text=text,
            preview=preview,
            file_path=str(file_path),
            uploaded_at=time.time(),
        )

    def upload_job_description_file(self, job_desc_file: Path) -> bool:
        logger.info("Uploading job description file: %s", job_desc_file)
        uploaded = False
        if click_button_by_patterns(self.page, BUTTON_PATTERNS["job_upload"], self.timeout):
            wait_for_navigation(self.page, self.timeout)
            uploaded = set_input_files(self.page, job_desc_file)

        if not uploaded:
            uploaded = set_input_files(self.page, job_desc_file)

        if uploaded:
            time.sleep(2)
            return True

        job_text = job_desc_file.read_text(encoding="utf-8")
        return fill_job_description_textarea(self.page, job_text)

    def enter_job_description(self, job_text: str, resume_name: Optional[str] = None) -> bool:
        logger.info("Entering job description in Report tab")
        dismiss_editing_conflict(self.page)

        if resume_name:
            self._open_dashboard()
            if self._open_resume_card_menu(resume_name):
                click_button_by_patterns(self.page, [r"tailor\s+to\s+jd"], self.timeout)
                self.page.wait_for_timeout(1500)
                if fill_job_description_textarea(self.page, job_text):
                    if click_button_by_patterns(self.page, BUTTON_PATTERNS["tailor"], self.timeout):
                        return self._wait_for_editor()

        if not navigate_to_report_tab(self.page, self.timeout):
            logger.error("Could not find Report tab in editor")
            return False

        if fill_job_description_textarea(self.page, job_text):
            logger.info("Job description entered in Report tab")
            return True

        logger.error("Could not find job description textarea")
        return False

    def get_score(self) -> Optional[int]:
        try:
            dismiss_editing_conflict(self.page)
            navigate_to_report_tab(self.page, self.timeout)
            return find_resume_score(self.page)
        except Exception as exc:
            logger.error("Error getting score: %s", exc)
            return None

    def trigger_analysis(self) -> bool:
        logger.info("Triggering resume analysis")
        dismiss_editing_conflict(self.page)
        navigate_to_report_tab(self.page, self.timeout)

        analyze_my = self.page.locator(
            "button:visible:not([disabled])",
            has_text=re.compile(r"analyze.my.resume", re.I),
        )
        if analyze_my.count():
            analyze_my.first.click(timeout=10000)
            time.sleep(10)
            return True

        if wait_and_click_reanalyse(self.page, max_wait=45):
            time.sleep(12)
            return True

        return click_button_by_patterns(self.page, BUTTON_PATTERNS["analyze"], self.timeout)

    def apply_ai_fixes(self, max_fixes: int = 5) -> int:
        dismiss_editing_conflict(self.page)
        navigate_to_report_tab(self.page, self.timeout)
        return apply_ai_suggestions(self.page, max_per_round=max_fixes)

    def get_report_feedback(self) -> ResumeFeedback:
        dismiss_editing_conflict(self.page)
        navigate_to_report_tab(self.page, self.timeout)
        wait_for_navigation(self.page, self.timeout)
        self.page.wait_for_timeout(1500)

        try:
            report_text = self.page.inner_text("body")
        except Exception:
            report_text = ""

        feedback = parse_feedback_text(report_text, score=find_resume_score(self.page))
        ai_buttons = self.page.locator(
            "button:visible:not([disabled])",
            has_text=re.compile(r"fix.with.ai|add.with.ai|add.all.to.skills", re.I),
        )
        if ai_buttons.count():
            for issue in feedback.issues:
                issue.fixable_with_ai = True
        return feedback

    def improve_until_target(
        self,
        target_score: int,
        max_attempts: int = 8,
        wait_between_attempts: int = 8,
    ) -> tuple[Optional[int], int]:
        """Improve score using Analyze -> AI suggestions -> Re-analyse loop."""
        from utils import improve_until_target as improve_page_until_target

        try:
            return improve_page_until_target(
                self.page,
                target_score=target_score,
                dry_run=False,
                timeout=self.timeout,
                max_attempts=max_attempts,
            )
        except RuntimeError:
            score = find_resume_score(self.page)
            return score, max_attempts

    def poll_score_until_target(
        self,
        target_score: int,
        max_attempts: int = 8,
        wait_between_attempts: int = 8,
    ) -> tuple[Optional[int], int]:
        """Alias for improve_until_target to preserve MCP API compatibility."""
        return self.improve_until_target(
            target_score=target_score,
            max_attempts=max_attempts,
            wait_between_attempts=wait_between_attempts,
        )

    def download_resume(
        self,
        output_dir: Path,
        resume_name: Optional[str] = None,
    ) -> Optional[Path]:
        logger.info("Downloading resume to %s", output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            self._open_dashboard()
            time.sleep(1)

            if not self._open_resume_card_menu(resume_name):
                logger.error("No resume cards found on dashboard")
                return None

            dl_menu = self.page.locator("button:visible", has_text=re.compile(r"^Download$", re.I))
            if not dl_menu.count():
                logger.error("Download option not found")
                return None

            dl_menu.first.click()
            self.page.wait_for_timeout(1500)

            portal = self.page.locator("#headlessui-portal-root")
            if portal.count() == 0:
                logger.error("Download dialog did not open")
                return None

            try:
                portal_text = portal.first.inner_text()
            except Exception:
                portal_text = ""
            if "Download Resume" not in portal_text:
                logger.warning("Unexpected download dialog: %s", portal_text[:80])

            fmt_select = portal.locator("select")
            if fmt_select.count():
                fmt_select.first.select_option("pdf")
                self.page.wait_for_timeout(400)

            with self.page.expect_download(timeout=self.timeout * 1000) as dl_info:
                portal.locator("button:visible", has_text=re.compile(r"^Download$", re.I)).click()

            dl = dl_info.value
            ts = time.strftime("%Y%m%d_%H%M%S")
            suggested = dl.suggested_filename or "tailored_resume.pdf"
            stem = suggested.rsplit(".", 1)[0] if "." in suggested else suggested
            out_path = output_dir / f"{stem}_tailored_{ts}.pdf"
            dl.save_as(str(out_path))
            logger.info("Resume downloaded: %s", out_path)
            return out_path
        except Exception as exc:
            logger.error("Error downloading resume: %s", exc)
            return None
