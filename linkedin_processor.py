"""LinkedIn browser automation and authentication."""

from __future__ import annotations

import logging
import time
from typing import Optional

from playwright.sync_api import Page, sync_playwright

from constants import (
    LINKEDIN_DEFAULT_TIMEOUT,
    LINKEDIN_JOBS_URL,
    LINKEDIN_LOGIN_URL,
    LINKEDIN_SESSION_DIR,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)

logger = logging.getLogger(__name__)


class LinkedInProcessor:
    """Handles Playwright browser lifecycle for LinkedIn automation."""

    def __init__(self, session_dir=None, timeout: int = LINKEDIN_DEFAULT_TIMEOUT):
        from pathlib import Path

        self.session_dir = Path(session_dir or LINKEDIN_SESSION_DIR)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.playwright = None
        self.browser_context = None
        self.page: Optional[Page] = None

    def init_browser(self, headless: bool = False) -> None:
        """Launch a persistent Chromium context."""
        logger.info("Initializing LinkedIn browser (headless=%s)", headless)
        self.playwright = sync_playwright().start()

        has_session = (self.session_dir / "Default" / "Cookies").exists()
        self.browser_context = self.playwright.chromium.launch_persistent_context(
            str(self.session_dir),
            headless=headless if has_session else False,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )
        self.page = self.browser_context.new_page()
        logger.info("LinkedIn browser initialized")

    def close_browser(self) -> None:
        """Close browser resources."""
        try:
            if self.browser_context:
                self.browser_context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            logger.error("Error closing LinkedIn browser: %s", exc)

    def is_logged_in(self) -> bool:
        """Return True when a LinkedIn feed or jobs page is accessible."""
        if self.page is None:
            return False

        url = self.page.url.lower()
        if "linkedin.com/login" in url or "linkedin.com/checkpoint" in url:
            return False

        indicators = [
            self.page.locator('button[aria-label*="Me"]').count() > 0,
            self.page.locator('img.global-nav__me-photo').count() > 0,
            self.page.locator('a[data-control-name="nav.settings"]').count() > 0,
            self.page.locator('nav.global-nav').count() > 0 and "feed" in url,
            "jobs" in url and "login" not in url,
        ]
        return any(indicators)

    def ensure_logged_in(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        wait_timeout_sec: int = 300,
    ) -> bool:
        """Ensure the user is authenticated on LinkedIn."""
        assert self.page is not None

        self.page.goto(LINKEDIN_JOBS_URL, timeout=self.timeout * 1000)
        self.page.wait_for_load_state("domcontentloaded")

        if self.is_logged_in():
            logger.info("Already signed in to LinkedIn")
            return True

        if email and password:
            return self._sign_in(email, password)

        return self._manual_login(wait_timeout_sec)

    def _sign_in(self, email: str, password: str) -> bool:
        """Attempt automated LinkedIn login."""
        assert self.page is not None
        logger.info("Signing in to LinkedIn as %s", email)

        self.page.goto(LINKEDIN_LOGIN_URL, timeout=self.timeout * 1000)
        self.page.fill("#username", email)
        self.page.fill("#password", password)
        self.page.click('button[type="submit"]')

        try:
            self.page.wait_for_url(
                lambda url: "login" not in url.lower(),
                timeout=self.timeout * 1000,
            )
        except Exception:
            logger.error("LinkedIn login did not complete within timeout")
            return False

        time.sleep(2)
        return self.is_logged_in()

    def _manual_login(self, wait_timeout_sec: int) -> bool:
        """Wait for the user to complete login in the browser."""
        assert self.page is not None
        logger.info("Waiting for manual LinkedIn login")

        self.page.goto(LINKEDIN_LOGIN_URL, timeout=self.timeout * 1000)
        deadline = time.time() + wait_timeout_sec

        while time.time() < deadline:
            if self.is_logged_in():
                logger.info("Manual LinkedIn login complete")
                return True
            time.sleep(2)

        logger.error("Manual LinkedIn login timed out")
        return False
