"""Scrape full job details from a LinkedIn job posting."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from linkedin_job_search import extract_job_id_from_url
from linkedin_processor import LinkedInProcessor
from models import JobDetails

logger = logging.getLogger(__name__)


def _first_text(page, selectors: list[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            try:
                text = locator.first.inner_text(timeout=3000).strip()
                if text:
                    return re.sub(r"\s+", " ", text)
            except Exception:
                continue
    return ""


def _expand_description(page) -> None:
    """Click 'Show more' if the job description is truncated."""
    for pattern in [r"show more", r"see more"]:
        button = page.get_by_role("button", name=re.compile(pattern, re.I))
        if button.count() > 0:
            try:
                button.first.click(timeout=3000)
                time.sleep(0.5)
            except Exception:
                pass


def get_job_details(processor: LinkedInProcessor, job_url: str) -> Optional[JobDetails]:
    """Open a LinkedIn job URL and extract posting details."""
    assert processor.page is not None
    page = processor.page

    normalized_url = job_url.split("?")[0]
    if "/jobs/view/" not in normalized_url:
        job_id = extract_job_id_from_url(job_url)
        normalized_url = f"https://www.linkedin.com/jobs/view/{job_id}"

    logger.info("Fetching LinkedIn job details: %s", normalized_url)
    page.goto(normalized_url, timeout=processor.timeout * 1000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    job_id = extract_job_id_from_url(page.url)

    title = _first_text(
        page,
        [
            "h1.job-details-jobs-unified-top-card__job-title",
            "h1.t-24",
            "h1",
            ".jobs-unified-top-card__job-title",
        ],
    )
    company = _first_text(
        page,
        [
            "a.job-details-jobs-unified-top-card__company-name",
            ".job-details-jobs-unified-top-card__company-name",
            ".jobs-unified-top-card__company-name a",
            ".jobs-unified-top-card__subtitle-primary-grouping a",
        ],
    )
    location = _first_text(
        page,
        [
            ".job-details-jobs-unified-top-card__bullet",
            ".jobs-unified-top-card__bullet",
            ".job-details-jobs-unified-top-card__primary-description-container",
        ],
    )

    _expand_description(page)

    description = _first_text(
        page,
        [
            ".show-more-less-html__markup",
            "#job-details",
            ".jobs-description__content",
            ".jobs-box__html-content",
            "article.jobs-description__container",
        ],
    )

    if not description:
        description = page.locator("body").inner_text(timeout=5000)
        description = description[:15000]

    easy_apply = (
        page.locator("button.jobs-apply-button").filter(has_text=re.compile(r"Easy Apply", re.I)).count() > 0
        or page.get_by_role("button", name=re.compile(r"Easy Apply", re.I)).count() > 0
    )

    if not title:
        logger.warning("Could not extract job title from %s", normalized_url)
        return None

    return JobDetails(
        job_id=job_id,
        title=title,
        company=company or "Unknown company",
        location=location or "",
        url=normalized_url,
        description=description,
        easy_apply=easy_apply,
    )
