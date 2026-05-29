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

    def get_editor_resume_text(self) -> str:
        dismiss_editing_conflict(self.page)
        for selector in ["[data-testid='resume-preview']", ".resume-preview", "article", "main"]:
            locator = self.page.locator(selector)
            if locator.count():
                try:
                    text = locator.first.inner_text(timeout=5000)
                    if text and len(text.strip()) > 100:
                        return text.strip()
                except Exception:
                    continue
        return self.page.inner_text("body").strip()

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

    def navigate_to_editor_tab(self) -> bool:
        """Switch to the Editor tab in the resume builder."""
        dismiss_editing_conflict(self.page)
        editor_tab = self.page.locator(
            "button:visible:not([disabled]), a:visible",
            has_text=re.compile(r"^Editor$", re.I),
        )
        if editor_tab.count() == 0:
            return False
        editor_tab.first.click(timeout=self.timeout * 1000)
        self.page.wait_for_timeout(1500)
        return True

    def _expand_section(self, section_name: str) -> None:
        header = self.page.locator(
            "button:visible, div:visible",
            has_text=re.compile(rf"^{re.escape(section_name)}$", re.I),
        )
        if header.count():
            try:
                header.first.click(timeout=5000)
                self.page.wait_for_timeout(800)
            except Exception:
                pass

    def _fill_input_by_label(self, label_pattern: str, value: str) -> bool:
        label = self.page.locator("label:visible", has_text=re.compile(label_pattern, re.I))
        if label.count() == 0:
            return False

        field_id = label.first.get_attribute("for")
        if field_id:
            field = self.page.locator(f"#{field_id}")
            if field.count():
                field.fill(value)
                return True

        container = label.first.locator("xpath=ancestor::*[self::div or self::section][1]")
        inputs = container.locator("textarea:visible, input:visible:not([type='file'])")
        if inputs.count():
            inputs.first.click()
            inputs.first.fill(value)
            return True
        return False

    def _fill_section_textareas(self, content: str) -> int:
        """Fill visible textareas in the currently expanded section."""
        updated = 0
        textareas = self.page.locator("textarea:visible")
        if textareas.count() == 1:
            textareas.first.click()
            textareas.first.fill(content)
            return 1

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            if idx >= textareas.count():
                break
            area = textareas.nth(idx)
            area.click()
            area.fill(line)
            updated += 1
        return updated

    def apply_resume_sections(self, sections: dict[str, str]) -> dict[str, bool]:
        """Apply parsed resume sections to the ResumeUp editor."""
        from resume_sections import parse_resume_sections

        if not self.navigate_to_editor_tab():
            raise RuntimeError("Could not open Editor tab")

        results: dict[str, bool] = {}

        if "Summary" in sections:
            self._expand_section("Summary")
            applied = self._fill_section_textareas(sections["Summary"])
            if not applied:
                applied = int(self._fill_input_by_label("headline|summary", sections["Summary"]))
            results["Summary"] = bool(applied)

        if "Skills" in sections:
            self._expand_section("Skills")
            results["Skills"] = bool(self._fill_section_textareas(sections["Skills"]))

        if "Work Experience" in sections:
            self._expand_section("Work Experience")
            results["Work Experience"] = bool(self._fill_section_textareas(sections["Work Experience"]))

        if "Education" in sections:
            self._expand_section("Education")
            results["Education"] = bool(self._fill_section_textareas(sections["Education"]))

        self.page.wait_for_timeout(1000)
        return results

    def apply_resume_text(self, resume_text: str) -> dict[str, bool]:
        """Parse and apply updated resume text to the editor."""
        from resume_sections import parse_resume_sections

        sections = parse_resume_sections(resume_text)
        if not sections:
            raise ValueError("No resume sections found in provided text")
        return self.apply_resume_sections(sections)

