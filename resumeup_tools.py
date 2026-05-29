"""ResumeUp.ai browser automation handlers."""

import re
import time
import logging
from typing import Optional
from pathlib import Path

from models import ResumeData
from utils import (
    click_button_by_patterns,
    set_input_files,
    wait_for_navigation,
    find_resume_score,
    navigate_to_report_tab,
    dismiss_editing_conflict,
    extract_resume_id_from_url,
    fill_job_description_textarea,
)
from constants import BUTTON_PATTERNS, DEFAULT_TIMEOUT, APP_URL

logger = logging.getLogger(__name__)


class ResumeUpHandler:
    """Handles Playwright interactions with ResumeUp.ai"""

    def __init__(self, page, timeout: int = DEFAULT_TIMEOUT):
        """Initialize handler with a Playwright page object."""
        self.page = page
        self.timeout = timeout

    def _open_dashboard(self) -> None:
        """Navigate to the ResumeUp dashboard."""
        self.page.goto(APP_URL, timeout=self.timeout * 1000)
        wait_for_navigation(self.page, self.timeout)
        dismiss_editing_conflict(self.page)

    def _wait_for_editor(self) -> bool:
        """Wait until the resume editor is loaded."""
        try:
            self.page.wait_for_url("**/resume-builder/**", timeout=self.timeout * 1000)
            wait_for_navigation(self.page, self.timeout)
            dismiss_editing_conflict(self.page)
            return True
        except Exception as exc:
            logger.error("Editor did not load: %s", exc)
            return False

    def _open_resume_card_menu(self, resume_name: Optional[str] = None) -> bool:
        """Open the three-dot menu on a dashboard resume card."""
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
        """Upload a resume file to ResumeUp."""
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

        logger.info("Resume file uploaded successfully")
        time.sleep(3)

        if not self._wait_for_editor():
            logger.warning("Upload succeeded but editor URL was not detected")

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

    def tailor_via_dashboard(self, job_text: str, resume_name: Optional[str] = None) -> bool:
        """Tailor a resume using the dashboard 'Tailor to JD' or 'Build Resume' flow."""
        logger.info("Starting dashboard tailor flow")
        self._open_dashboard()

        opened = False
        if resume_name and self._open_resume_card_menu(resume_name):
            opened = click_button_by_patterns(
                self.page,
                [r"tailor\s+to\s+jd"],
                self.timeout,
            )

        if not opened:
            opened = click_button_by_patterns(
                self.page,
                BUTTON_PATTERNS["tailor"],
                self.timeout,
            )

        if not opened:
            logger.error("Could not open tailor dialog from dashboard")
            return False

        self.page.wait_for_timeout(1500)

        if not fill_job_description_textarea(self.page, job_text):
            logger.error("Could not find job description field in tailor dialog")
            return False

        if not click_button_by_patterns(self.page, BUTTON_PATTERNS["tailor"], self.timeout):
            logger.error("Could not click Build Resume")
            return False

        if not self._wait_for_editor():
            return False

        logger.info("Dashboard tailor flow completed")
        return True

    def enter_job_description(self, job_text: str, resume_name: Optional[str] = None) -> bool:
        """Enter a job description via dashboard tailor flow or Report tab fallback."""
        logger.info("Entering job description")

        if self.tailor_via_dashboard(job_text, resume_name=resume_name):
            return True

        try:
            dismiss_editing_conflict(self.page)

            if not navigate_to_report_tab(self.page, self.timeout):
                logger.error("Could not find Report tab in editor")
                return False

            if fill_job_description_textarea(self.page, job_text):
                logger.info("Job description entered in Report tab")
                return True

            logger.error("Could not find job description textarea")
            return False
        except Exception as exc:
            logger.error("Error entering job description: %s", exc)
            return False

    def get_score(self) -> Optional[int]:
        """Get current resume score from ResumeUp."""
        try:
            dismiss_editing_conflict(self.page)
            navigate_to_report_tab(self.page, self.timeout)
            return find_resume_score(self.page)
        except Exception as exc:
            logger.error("Error getting score: %s", exc)
            return None

    def trigger_analysis(self) -> bool:
        """Trigger resume analysis in ResumeUp."""
        logger.info("Triggering resume analysis")

        try:
            dismiss_editing_conflict(self.page)
            navigate_to_report_tab(self.page, self.timeout)
            wait_for_navigation(self.page, self.timeout)

            clicked = click_button_by_patterns(
                self.page,
                BUTTON_PATTERNS["analyze"],
                self.timeout,
            )

            if clicked:
                logger.info("Analysis triggered successfully")
                self.page.wait_for_timeout(3000)
                return True

            logger.warning("Could not find analysis button")
            return False
        except Exception as exc:
            logger.error("Error triggering analysis: %s", exc)
            return False

    def poll_score_until_target(
        self,
        target_score: int,
        max_attempts: int = 8,
        wait_between_attempts: int = 8,
    ) -> tuple[Optional[int], int]:
        """Poll resume score until target is reached or max attempts exceeded."""
        logger.info(
            "Polling score until %s (max %s attempts)",
            target_score,
            max_attempts,
        )

        best_score = None
        attempts = 0

        while attempts < max_attempts:
            attempts += 1
            dismiss_editing_conflict(self.page)

            if not navigate_to_report_tab(self.page, 30):
                logger.warning("Report tab not ready")
                time.sleep(wait_between_attempts)
                continue

            wait_for_navigation(self.page, self.timeout)
            score = find_resume_score(self.page)

            if score is not None:
                best_score = score
                logger.info("Score check %s/%s: %s", attempts, max_attempts, score)

                if score >= target_score:
                    logger.info("Target score %s reached!", target_score)
                    return score, attempts
            else:
                logger.warning("Could not detect score on attempt %s", attempts)

            if attempts < max_attempts:
                logger.info("Triggering analysis round %s", attempts + 1)
                if not self.trigger_analysis():
                    logger.warning("Failed to trigger analysis")
                    break
                time.sleep(wait_between_attempts)

        logger.info("Polling complete. Best score: %s", best_score)
        return best_score, attempts

    def download_resume(
        self,
        output_dir: Path,
        resume_name: Optional[str] = None,
    ) -> Optional[Path]:
        """Download tailored resume as PDF from the dashboard menu."""
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
            if not portal.count():
                logger.error("Download dialog did not open")
                return None

            fmt_select = portal.locator("select")
            if fmt_select.count():
                fmt_select.first.select_option("pdf")
                self.page.wait_for_timeout(400)

            logger.info("Initiating PDF download")
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
