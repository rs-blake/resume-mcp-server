"""Resume processor for handling browser automation and authentication."""

import re
import logging
import os
from typing import Optional
from pathlib import Path
from playwright.sync_api import sync_playwright

from utils import is_signed_in, wait_for_navigation
from constants import LOGIN_URL, APP_URL, DEFAULT_TIMEOUT, SESSION_DIR, VIEWPORT_WIDTH, VIEWPORT_HEIGHT

logger = logging.getLogger(__name__)


class ResumeProcessor:
    """Handles browser initialization and authentication with ResumeUp."""
    
    def __init__(self, session_dir: Optional[Path] = None, timeout: int = DEFAULT_TIMEOUT):
        """Initialize processor.
        
        Args:
            session_dir: Directory for persistent session storage
            timeout: Default timeout in seconds
        """
        self.session_dir = Path(session_dir or SESSION_DIR)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.playwright = None
        self.browser_context = None
        self.page = None
    
    def init_browser(self, headless: bool = False):
        """Initialize Playwright browser.
        
        Args:
            headless: Run browser in headless mode
        """
        logger.info(f"Initializing Playwright browser (headless={headless})")
        
        self.playwright = sync_playwright().start()
        
        # Check if we have a persisted session
        has_session = (self.session_dir / "Default" / "Cookies").exists()
        
        self.browser_context = self.playwright.chromium.launch_persistent_context(
            str(self.session_dir),
            headless=headless if has_session else False,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )
        
        self.page = self.browser_context.new_page()
        logger.info("Browser initialized")
    
    def close_browser(self):
        """Close browser and cleanup."""
        try:
            if self.browser_context:
                self.browser_context.close()
                logger.info("Browser context closed")
            
            if self.playwright:
                self.playwright.stop()
                logger.info("Playwright stopped")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
    
    def sign_in(self, email: str, password: str) -> bool:
        """Sign in to ResumeUp with email and password.
        
        Args:
            email: ResumeUp email
            password: ResumeUp password
            
        Returns:
            True if signed in successfully, False otherwise
        """
        try:
            logger.info(f"Signing in as {email}")
            
            self.page.goto(LOGIN_URL, timeout=self.timeout * 1000)
            self.page.wait_for_selector('#email-signin', timeout=self.timeout * 1000)
            
            self.page.fill('#email-signin', email)
            self.page.fill('#password-signin', password)
            
            login_button = self.page.get_by_role("button", name=re.compile(r"login", re.I))
            if login_button.count() == 0:
                logger.error("Login button not found")
                return False
            
            login_button.first.click()
            
            # Wait for redirect from signin page
            try:
                self.page.wait_for_url(
                    lambda url: "signin" not in url.lower(),
                    timeout=self.timeout * 1000
                )
            except Exception:
                logger.error("Login did not complete within timeout")
                return False
            
            wait_for_navigation(self.page, self.timeout)
            
            if not is_signed_in(self.page):
                logger.error("Sign-in failed - still on signin page")
                return False
            
            logger.info("Signed in successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error during sign-in: {e}")
            return False
    
    def manual_login(self) -> bool:
        """Prompt for manual login to ResumeUp.
        
        Returns:
            True if user successfully logs in, False on timeout
        """
        logger.info("Opening browser for manual login")
        logger.info("Please log in to ResumeUp in the opened browser window")
        
        self.page.goto(LOGIN_URL)
        
        try:
            self.page.wait_for_url(
                lambda url: "signin" not in url.lower(),
                timeout=self.timeout * 1000
            )
        except Exception:
            logger.error("Manual login did not complete within timeout")
            return False
        
        wait_for_navigation(self.page, self.timeout)
        logger.info("Manual login complete")
        return True
    
    def navigate_to_editor(self, resume_id: str) -> bool:
        """Navigate to resume editor using resume ID.
        
        Args:
            resume_id: ResumeUp resume UUID
            
        Returns:
            True if navigation successful, False otherwise
        """
        try:
            editor_url = f"https://app.resumeup.ai/resume-builder/{resume_id}"
            logger.info(f"Navigating to editor: {editor_url}")
            
            self.page.goto(editor_url, timeout=self.timeout * 1000)
            wait_for_navigation(self.page, self.timeout)
            
            logger.info("Editor loaded")
            return True
        except Exception as e:
            logger.error(f"Error navigating to editor: {e}")
            return False
    
    def select_template(self) -> bool:
        """Select a resume template if in template selection step.
        
        Returns:
            True if template selected or already in editor, False on error
        """
        try:
            # Check if we're already in the editor
            if "/resume-builder/" in self.page.url:
                logger.info("Already in resume editor")
                return True
            
            logger.info("Selecting template...")
            
            # Try common template selection patterns
            for pattern in [
                r"ATS.Friendly", r"ATS Friendly",
                r"Craft", r"Catalyst", r"Luminary",
                r"Use Template", r"Use This",
                r"Continue", r"Next",
            ]:
                loc = self.page.locator("button:visible:not([disabled])", has_text=re.compile(pattern, re.I))
                if loc.count() > 0:
                    try:
                        loc.first.click(timeout=10000)
                        break
                    except Exception:
                        continue
            
            # Wait for editor to load
            self.page.wait_for_url("**/resume-builder/**", timeout=self.timeout * 1000)
            wait_for_navigation(self.page, self.timeout)
            
            logger.info("Template selected and editor loaded")
            return True
        
        except Exception as e:
            logger.error(f"Error selecting template: {e}")
            return False
    
    def ensure_logged_in(self, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Ensure user is logged in to ResumeUp.
        
        If email and password are provided, attempts automated login.
        Otherwise, prompts for manual login.
        
        Args:
            email: Optional email for automated login
            password: Optional password for automated login
            
        Returns:
            True if logged in, False otherwise
        """
        self.page.goto(APP_URL, timeout=self.timeout * 1000)
        wait_for_navigation(self.page, self.timeout)
        
        if is_signed_in(self.page):
            logger.info("Already signed in")
            return True
        
        if email and password:
            return self.sign_in(email, password)
        else:
            return self.manual_login()
