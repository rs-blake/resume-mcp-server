"""LinkedIn job search URL building and result scraping."""

from __future__ import annotations

import logging
import re
import time
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from constants import (
    LINKEDIN_FILTER_EASY_APPLY,
    LINKEDIN_FILTER_REMOTE,
    LINKEDIN_JOBS_URL,
    LINKEDIN_REMOTE_VALUE,
)
from linkedin_processor import LinkedInProcessor
from models import JobListing

logger = logging.getLogger(__name__)


def build_search_url(
    keywords: str,
    location: str = "",
    easy_apply_only: bool = True,
    remote_only: bool = False,
    start: int = 0,
) -> str:
    """Build a LinkedIn jobs search URL."""
    params = {"keywords": keywords.strip()}
    if location.strip():
        params["location"] = location.strip()
    if start > 0:
        params["start"] = str(start)

    filters: List[str] = []
    if easy_apply_only:
        params[LINKEDIN_FILTER_EASY_APPLY] = "true"
    if remote_only:
        params[LINKEDIN_FILTER_REMOTE] = LINKEDIN_REMOTE_VALUE

    return f"{LINKEDIN_JOBS_URL}search/?{urlencode(params)}"


def extract_job_id_from_url(url: str) -> str:
    """Extract numeric LinkedIn job ID from a job URL."""
    match = re.search(r"/jobs/view/(\d+)", url)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "currentJobId" in query:
        return query["currentJobId"][0]

    match = re.search(r"(\d{6,})", url)
    return match.group(1) if match else url


def _scroll_results(page, scrolls: int = 4) -> None:
    """Scroll the job results list to load more cards."""
    for _ in range(scrolls):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1.2)


def _parse_result_cards(page) -> List[JobListing]:
    """Parse visible job cards from a LinkedIn search results page."""
    listings: List[JobListing] = []
    seen_ids: set[str] = set()

    card_selectors = [
        "li.scaffold-layout__list-item",
        "li.jobs-search-results__list-item",
        "div.job-card-container",
        "ul.scaffold-layout__list-container > li",
    ]

    cards = None
    for selector in card_selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            cards = locator
            break

    if cards is None:
        logger.warning("No LinkedIn job result cards found")
        return listings

    count = min(cards.count(), 50)
    for index in range(count):
        card = cards.nth(index)
        try:
            link = card.locator("a[href*='/jobs/view/']").first
            if link.count() == 0:
                link = card.locator("a.base-card__full-link").first
            if link.count() == 0:
                continue

            href = link.get_attribute("href") or ""
            if not href:
                continue

            url = href.split("?")[0]
            if not url.startswith("http"):
                url = f"https://www.linkedin.com{url}"

            job_id = extract_job_id_from_url(url)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title = _first_text(
                card,
                [
                    ".job-card-list__title",
                    ".base-search-card__title",
                    "strong",
                    "h3",
                    "a[href*='/jobs/view/']",
                ],
            )
            company = _first_text(
                card,
                [
                    ".job-card-container__company-name",
                    ".base-search-card__subtitle",
                    ".artdeco-entity-lockup__subtitle",
                ],
            )
            location = _first_text(
                card,
                [
                    ".job-card-container__metadata-item",
                    ".job-search-card__location",
                    ".artdeco-entity-lockup__caption",
                ],
            )

            easy_apply = (
                card.locator("text=/Easy Apply/i").count() > 0
                or card.locator("li-icon[type='linkedin-bug']").count() > 0
            )

            listings.append(
                JobListing(
                    job_id=job_id,
                    title=title or "Unknown title",
                    company=company or "Unknown company",
                    location=location or "",
                    url=url,
                    easy_apply=easy_apply,
                )
            )
        except Exception as exc:
            logger.debug("Failed to parse job card %s: %s", index, exc)

    return listings


def _first_text(parent, selectors: List[str]) -> str:
    """Return trimmed text from the first matching selector."""
    for selector in selectors:
        locator = parent.locator(selector)
        if locator.count() > 0:
            text = locator.first.inner_text(timeout=2000).strip()
            if text:
                return re.sub(r"\s+", " ", text)
    return ""


def search_jobs(
    processor: LinkedInProcessor,
    keywords: str,
    location: str = "",
    easy_apply_only: bool = True,
    remote_only: bool = False,
    limit: int = 20,
) -> List[JobListing]:
    """Search LinkedIn jobs and return parsed listings."""
    assert processor.page is not None
    page = processor.page

    collected: List[JobListing] = []
    seen_ids: set[str] = set()
    start = 0

    while len(collected) < limit and start <= 100:
        url = build_search_url(
            keywords=keywords,
            location=location,
            easy_apply_only=easy_apply_only,
            remote_only=remote_only,
            start=start,
        )
        logger.info("Searching LinkedIn jobs: %s", url)
        page.goto(url, timeout=processor.timeout * 1000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(2)

        _scroll_results(page)
        batch = _parse_result_cards(page)

        for listing in batch:
            if listing.job_id in seen_ids:
                continue
            if easy_apply_only and not listing.easy_apply:
                continue
            seen_ids.add(listing.job_id)
            collected.append(listing)
            if len(collected) >= limit:
                break

        if not batch:
            break
        start += 25

    logger.info("Found %s LinkedIn job listings", len(collected))
    return collected[:limit]
