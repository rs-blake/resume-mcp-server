"""ResumeUp.ai browser automation handlers."""

import re
import time
import logging
import uuid
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
)
from constants import BUTTON_PATTERNS, DEFAULT_TIMEOUT, APP_URL

logger = logging.getLogger(__name__)


class ResumeUpHandler:
    """Handles Playwright interactions with ResumeUp.ai"""
    
    def __init__(self, page, timeout: int = DEFAULT_TIMEOUT):
        """Initialize handler with a Playwright page object.
        
        Args:
            page: Playwright page object
            timeout: Default timeout in seconds
        """
        self.page = page
        self.timeout = timeout
    
    def upload_resume(self, file_path: Path) -> Optional[ResumeData]:
        """Upload a resume file to ResumeUp.
        
        Args:
            file_path: Path to resume file (PDF, DOCX, TXT)
            
        Returns:
            ResumeData object if successful, None otherwise
        """
        logger.info(f"Uploading resume: {file_path}")
        
        if not file_path.exists():
            logger.error(f"Resume file not found: {file_path}")
            return None
        
        self.page.goto(APP_URL, timeout=self.timeout * 1000)
        wait_for_navigation(self.page, self.timeout)
        
        # Try to find and click upload button
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
        time.sleep(2)
        
        # Extract resume text if possible
        try:
            text = self.page.inner_text("body")
            preview = text[:500] if text else ""
            
            resume = ResumeData(
                id=str(uuid.uuid4()),
                text=text,
                preview=preview,
                file_path=str(file_path),
                uploaded_at=time.time()
            )
            return resume
        except Exception as e:
            logger.error(f"Error extracting resume data: {e}")
            return None
    
    def enter_job_description(self, job_text: str) -> bool:
        """Enter job description in ResumeUp editor.
        
        Args:
            job_text: Full job description text
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Entering job description in editor")
        
        try:
            # Navigate to Report tab
            report_tab = self.page.locator(
                "button:visible, a:visible",
                has_text=re.compile(r"^Report$", re.I)
            )
            
            if not report_tab.count():
                report_tab = self.page.locator(
                    "button, a",
                    has_text=re.compile(r"report", re.I)
                )
            
            if not report_tab.count():
                logger.error("Could not find Report tab in editor")
                return False
            
            report_tab.first.click()
            self.page.wait_for_timeout(1500)
            
            # Find and fill job description textarea
            textareas = self.page.locator("textarea:visible")
            for idx in range(textareas.count()):
                area = textareas.nth(idx)
                placeholder = (area.get_attribute("placeholder") or "").lower()
                aria = (area.get_attribute("aria-label") or "").lower()
                
                if any(k in placeholder or k in aria for k in ("job", "description", "jd")):
                    area.triple_click()
                    area.fill(job_text)
                    logger.info("Job description entered in editor")
                    return True
            
            # Fallback: use first textarea
            if textareas.count() > 0:
                textareas.first.triple_click()
                textareas.first.fill(job_text)
                logger.info("Job description entered (fallback textarea)")
                return True
            
            logger.error("Could not find job description textarea")
            return False
        
        except Exception as e:
            logger.error(f"Error entering job description: {e}")
            return False
    
    def get_score(self) -> Optional[int]:
        """Get current resume score from ResumeUp.
        
        Returns:
            Score (0-100) or None if not found
        """
        try:
            navigate_to_report_tab(self.page, self.timeout)
            return find_resume_score(self.page)
        except Exception as e:
            logger.error(f"Error getting score: {e}")
            return None
    
    def trigger_analysis(self) -> bool:
        """Trigger resume analysis in ResumeUp.
        
        Returns:
            True if analysis was triggered, False otherwise
        """
        logger.info("Triggering resume analysis")
        
        try:
            navigate_to_report_tab(self.page, self.timeout)
            wait_for_navigation(self.page, self.timeout)
            
            clicked = click_button_by_patterns(
                self.page,
                BUTTON_PATTERNS["analyze"],
                self.timeout
            )
            
            if clicked:
                logger.info("Analysis triggered successfully")
                return True
            
            logger.warning("Could not find analysis button")
            return False
        
        except Exception as e:
            logger.error(f"Error triggering analysis: {e}")
            return False
    
    def poll_score_until_target(
        self,
        target_score: int,
        max_attempts: int = 8,
        wait_between_attempts: int = 8
    ) -> Optional[int]:
        """Poll resume score until target is reached or max attempts exceeded.
        
        Args:
            target_score: Target score to reach
            max_attempts: Maximum number of polling attempts
            wait_between_attempts: Seconds to wait between attempts
            
        Returns:
            Final score reached or None if error
        """
        logger.info(f"Polling score until {target_score} (max {max_attempts} attempts)")
        
        best_score = None
        attempts = 0
        
        while attempts < max_attempts:
            attempts += 1
            
            # Dismiss any editing conflicts
            dismiss_editing_conflict(self.page)
            
            # Navigate to report tab and check score
            if not navigate_to_report_tab(self.page, 30):
                logger.warning("Report tab not ready")
                time.sleep(wait_between_attempts)
                continue
            
            wait_for_navigation(self.page, self.timeout)
            
            score = self.get_score()
            if score is not None:
                best_score = score
                logger.info(f"Score check {attempts}/{max_attempts}: {score}")
                
                if score >= target_score:
                    logger.info(f"Target score {target_score} reached!")
                    return score
            else:
                logger.warning(f"Could not detect score on attempt {attempts}")
            
            # Trigger another analysis round
            if attempts < max_attempts:
                logger.info(f"Triggering analysis round {attempts + 1}")
                if not self.trigger_analysis():
                    logger.warning("Failed to trigger analysis")
                    break
                
                time.sleep(wait_between_attempts)
        
        logger.info(f"Polling complete. Best score: {best_score}")
        return best_score
    
    def download_resume(self, output_dir: Path) -> Optional[Path]:
        """Download tailored resume as PDF.
        
        Args:
            output_dir: Directory to save PDF
            
        Returns:
            Path to downloaded file or None on failure
        """
        logger.info(f"Downloading resume to {output_dir}")
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Navigate to dashboard
            self.page.goto(APP_URL, timeout=self.timeout * 1000)
            wait_for_navigation(self.page, self.timeout)
            time.sleep(1)
            
            # Open resume card menu
            dots = self.page.locator("button", has_text="...")
            if not dots.count():
                logger.error("No resume cards found on dashboard")
                return None
            
            dots.first.click()
            self.page.wait_for_timeout(800)
            
            # Click Download option
            dl_menu = self.page.locator("button:visible", has_text="Download")
            if not dl_menu.count():
                logger.error("Download option not found")
                return None
            
            dl_menu.first.click()
            self.page.wait_for_timeout(1500)
            
            # Verify download dialog
            portal = self.page.locator("#headlessui-portal-root")
            if not portal.count():
                logger.error("Download dialog did not open")
                return None
            
            # Select PDF format
            fmt_select = portal.locator("select")
            if fmt_select.count():
                fmt_select.first.select_option("pdf")
                self.page.wait_for_timeout(400)
            
            # Trigger download
            logger.info("Initiating PDF download")
            try:
                with self.page.expect_download(timeout=self.timeout * 1000) as dl_info:
                    portal.locator("button:visible", has_text="Download").click()
                
                dl = dl_info.value
                ts = time.strftime("%Y%m%d_%H%M%S")
                suggested = dl.suggested_filename or "tailored_resume.pdf"
                stem = suggested.rsplit(".", 1)[0] if "." in suggested else suggested
                out_path = output_dir / f"{stem}_tailored_{ts}.pdf"
                dl.save_as(str(out_path))
                
                logger.info(f"Resume downloaded: {out_path}")
                return out_path
            
            except Exception as e:
                logger.error(f"Download failed: {e}")
                return None
        
        except Exception as e:
            logger.error(f"Error downloading resume: {e}")
            return None
