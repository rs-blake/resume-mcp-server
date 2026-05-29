"""Orchestrate LinkedIn search, ResumeUp tailoring, and application queue."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from application_store import (
    create_application,
    get_application,
    has_applied_to_job,
    list_applications,
    save_application,
    update_application_status,
)
from constants import APPLICATIONS_OUTPUT_DIR
from job_matcher import compute_match_score, matched_skills, missing_skills
from job_parser import extract_skills_from_text, parse_job_description
from linkedin_easy_apply import run_easy_apply
from linkedin_job_scraper import get_job_details
from linkedin_job_search import search_jobs
from linkedin_processor import LinkedInProcessor
from resumeup_workflow import run_tailor_and_download

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return slug.strip("-")[:60] or "job"


def _resolve_profile_skills(profile_skills: Optional[List[str]]) -> List[str]:
    if profile_skills:
        return profile_skills

    env_skills = os.getenv("PROFILE_SKILLS", "")
    if env_skills.strip():
        return [skill.strip() for skill in env_skills.split(",") if skill.strip()]

    return []


def _load_profile_defaults() -> Dict[str, str]:
    profile_path = os.getenv("APPLICATION_PROFILE_PATH")
    if profile_path:
        path = Path(os.path.expanduser(profile_path))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

    return {
        "work_authorization": os.getenv("PROFILE_WORK_AUTHORIZATION", "Yes"),
        "requires_sponsorship": os.getenv("PROFILE_REQUIRES_SPONSORSHIP", "No"),
        "years_experience": os.getenv("PROFILE_YEARS_EXPERIENCE", ""),
    }


def run_search_and_tailor(
    keywords: str,
    location: str = "",
    easy_apply_only: bool = True,
    remote_only: bool = False,
    limit: int = 5,
    min_match_score: float = 0.0,
    profile_skills: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    resume_session_id: Optional[str] = None,
    file_path: Optional[str] = None,
    resume_id: Optional[str] = None,
    resume_name: Optional[str] = None,
    target_score: int = 95,
    max_attempts: int = 8,
    linkedin_email: Optional[str] = None,
    linkedin_password: Optional[str] = None,
    headless: Optional[bool] = None,
    close_linkedin_session: bool = True,
) -> Dict[str, Any]:
    """Search LinkedIn, tailor matching jobs via ResumeUp, and populate the review queue."""
    skills = _resolve_profile_skills(profile_skills)
    base_output = Path(os.path.expanduser(output_dir or APPLICATIONS_OUTPUT_DIR))
    base_output.mkdir(parents=True, exist_ok=True)

    linkedin = LinkedInProcessor()
    linkedin_headless = headless
    if linkedin_headless is None:
        linkedin_headless = os.getenv("LINKEDIN_HEADLESS", "false").lower() in {"1", "true", "yes"}

    results: List[Dict[str, Any]] = []
    tailored_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        linkedin.init_browser(headless=linkedin_headless)
        creds_email = linkedin_email or os.getenv("LINKEDIN_EMAIL")
        creds_password = linkedin_password or os.getenv("LINKEDIN_PASSWORD")

        if not linkedin.ensure_logged_in(creds_email, creds_password):
            return {"success": False, "message": "Failed to authenticate with LinkedIn"}

        listings = search_jobs(
            linkedin,
            keywords=keywords,
            location=location,
            easy_apply_only=easy_apply_only,
            remote_only=remote_only,
            limit=limit * 3,
        )

        processed = 0
        for listing in listings:
            if processed >= limit:
                break

            if has_applied_to_job(listing.job_id):
                skipped_count += 1
                results.append(
                    {
                        "job_id": listing.job_id,
                        "title": listing.title,
                        "status": "skipped",
                        "reason": "already_in_queue",
                    }
                )
                continue

            details = get_job_details(linkedin, listing.url)
            if details is None:
                failed_count += 1
                application = create_application(
                    job_id=listing.job_id,
                    job_url=listing.url,
                    title=listing.title,
                    company=listing.company,
                    location=listing.location,
                    easy_apply=listing.easy_apply,
                    status="failed",
                )
                application.error_message = "Could not scrape job details"
                save_application(application)
                results.append(
                    {
                        "application_id": application.application_id,
                        "job_id": listing.job_id,
                        "status": "failed",
                        "reason": application.error_message,
                    }
                )
                continue

            parsed = parse_job_description(details.description)
            job_skills = parsed.key_skills or extract_skills_from_text(details.description)
            match_score = compute_match_score(job_skills, skills) if skills else 1.0

            if match_score < min_match_score:
                skipped_count += 1
                application = create_application(
                    job_id=details.job_id,
                    job_url=details.url,
                    title=details.title,
                    company=details.company,
                    location=details.location,
                    easy_apply=details.easy_apply,
                    status="skipped",
                )
                application.match_score = match_score
                application.error_message = f"Match score {match_score} below minimum {min_match_score}"
                save_application(application)
                results.append(
                    {
                        "application_id": application.application_id,
                        "job_id": details.job_id,
                        "title": details.title,
                        "status": "skipped",
                        "match_score": match_score,
                        "reason": application.error_message,
                    }
                )
                continue

            job_dir = base_output / f"{details.job_id}-{_slugify(details.company)}"
            job_dir.mkdir(parents=True, exist_ok=True)
            jd_path = job_dir / "job_description.txt"
            jd_path.write_text(details.description, encoding="utf-8")

            application = create_application(
                job_id=details.job_id,
                job_url=details.url,
                title=details.title,
                company=details.company,
                location=details.location,
                easy_apply=details.easy_apply,
                status="tailoring",
            )
            application.match_score = match_score
            application.job_description_path = str(jd_path)
            save_application(application)

            tailor_result = run_tailor_and_download(
                job_description_text=details.description,
                session_id=resume_session_id,
                file_path=file_path,
                resume_id=resume_id,
                resume_name=resume_name,
                target_score=target_score,
                max_attempts=max_attempts,
                output_dir=str(job_dir),
                close_session=False,
            )

            if tailor_result.get("success"):
                tailored_count += 1
                update_application_status(
                    application.application_id,
                    "tailored",
                    resume_score=tailor_result.get("final_score"),
                    pdf_path=tailor_result.get("file_path"),
                    match_score=match_score,
                )
                results.append(
                    {
                        "application_id": application.application_id,
                        "job_id": details.job_id,
                        "title": details.title,
                        "company": details.company,
                        "status": "tailored",
                        "match_score": match_score,
                        "matched_skills": matched_skills(job_skills, skills),
                        "missing_skills": missing_skills(job_skills, skills),
                        "resume_score": tailor_result.get("final_score"),
                        "pdf_path": tailor_result.get("file_path"),
                        "job_description_path": str(jd_path),
                    }
                )
            else:
                failed_count += 1
                update_application_status(
                    application.application_id,
                    "failed",
                    match_score=match_score,
                    error_message=tailor_result.get("message", "Tailoring failed"),
                )
                results.append(
                    {
                        "application_id": application.application_id,
                        "job_id": details.job_id,
                        "title": details.title,
                        "status": "failed",
                        "match_score": match_score,
                        "reason": tailor_result.get("message"),
                    }
                )

            processed += 1

        return {
            "success": True,
            "keywords": keywords,
            "location": location,
            "tailored_count": tailored_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "results": results,
            "message": (
                f"Processed {processed} job(s): "
                f"{tailored_count} tailored, {skipped_count} skipped, {failed_count} failed"
            ),
        }
    finally:
        if close_linkedin_session:
            linkedin.close_browser()


def run_apply_from_queue(
    application_id: str,
    require_approval: bool = True,
    submit: bool = False,
    max_custom_questions: int = 3,
    linkedin_email: Optional[str] = None,
    linkedin_password: Optional[str] = None,
    headless: Optional[bool] = None,
    close_linkedin_session: bool = True,
) -> Dict[str, Any]:
    """Run LinkedIn Easy Apply for a queued application."""
    application = get_application(application_id=application_id)
    if application is None:
        return {"success": False, "message": f"Application not found: {application_id}"}

    if application.status not in {"tailored", "approved"}:
        return {
            "success": False,
            "message": f"Application status must be tailored or approved, got: {application.status}",
        }

    if not application.pdf_path:
        return {"success": False, "message": "No tailored PDF found for this application"}

    linkedin = LinkedInProcessor()
    linkedin_headless = headless
    if linkedin_headless is None:
        linkedin_headless = os.getenv("LINKEDIN_HEADLESS", "false").lower() in {"1", "true", "yes"}

    try:
        linkedin.init_browser(headless=linkedin_headless)
        creds_email = linkedin_email or os.getenv("LINKEDIN_EMAIL")
        creds_password = linkedin_password or os.getenv("LINKEDIN_PASSWORD")

        if not linkedin.ensure_logged_in(creds_email, creds_password):
            return {"success": False, "message": "Failed to authenticate with LinkedIn"}

        apply_result = run_easy_apply(
            linkedin,
            job_url=application.job_url,
            resume_path=application.pdf_path,
            profile=_load_profile_defaults(),
            require_approval=require_approval,
            max_custom_questions=max_custom_questions,
            submit=submit,
        )

        if apply_result.get("submitted"):
            update_application_status(application_id, "applied")
        elif apply_result.get("ready_to_submit"):
            update_application_status(application_id, "approved")
        elif not apply_result.get("success"):
            update_application_status(
                application_id,
                application.status,
                error_message=apply_result.get("message"),
            )

        return {
            **apply_result,
            "application_id": application_id,
            "job_url": application.job_url,
            "pdf_path": application.pdf_path,
        }
    finally:
        if close_linkedin_session:
            linkedin.close_browser()


def get_application_history(
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Return queued applications for review."""
    applications = list_applications(status=status, limit=limit)
    return {
        "success": True,
        "count": len(applications),
        "applications": [app.to_dict() for app in applications],
    }
