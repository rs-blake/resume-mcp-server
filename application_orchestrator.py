"""Orchestrate LinkedIn search, ResumeUp tailoring, and application queue."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from application_profile import load_application_profile, validate_profile_for_apply
from application_store import (
    count_tailored_today,
    create_application,
    export_applications_csv,
    get_application,
    has_applied_to_job,
    has_duplicate_company_title,
    list_applications,
    save_application,
    update_application_status,
)
from constants import (
    APPLICATIONS_OUTPUT_DIR,
    DAILY_TAILOR_CAP,
    DEFAULT_MAX_CUSTOM_QUESTIONS,
    DEFAULT_MIN_MATCH_SCORE,
    DEFAULT_SEARCH_LIMIT,
    USE_LLM_SCREENING,
)
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


def _load_profile_defaults() -> Dict[str, Any]:
    return load_application_profile()


def run_search_and_tailor(
    keywords: str,
    location: str = "",
    easy_apply_only: bool = True,
    remote_only: bool = False,
    limit: Optional[int] = None,
    min_match_score: Optional[float] = None,
    profile_skills: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    resume_session_id: Optional[str] = None,
    file_path: Optional[str] = None,
    resume_id: Optional[str] = None,
    resume_name: Optional[str] = None,
    target_score: int = 95,
    max_attempts: int = 8,
    daily_cap: Optional[int] = None,
    dedupe_company_title: bool = True,
    linkedin_email: Optional[str] = None,
    linkedin_password: Optional[str] = None,
    headless: Optional[bool] = None,
    close_linkedin_session: bool = True,
) -> Dict[str, Any]:
    """Search LinkedIn, tailor matching jobs via ResumeUp, and populate the review queue."""
    resolved_limit = limit if limit is not None else DEFAULT_SEARCH_LIMIT
    resolved_min_score = min_match_score if min_match_score is not None else DEFAULT_MIN_MATCH_SCORE
    resolved_daily_cap = daily_cap if daily_cap is not None else DAILY_TAILOR_CAP

    already_today = count_tailored_today()
    remaining_cap = max(resolved_daily_cap - already_today, 0)
    if remaining_cap <= 0:
        return {
            "success": False,
            "message": (
                f"Daily tailor cap reached ({resolved_daily_cap}). "
                f"Already processed {already_today} job(s) today."
            ),
            "daily_cap": resolved_daily_cap,
            "tailored_today": already_today,
        }

    effective_limit = min(resolved_limit, remaining_cap)
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
            limit=effective_limit * 3,
        )

        processed = 0
        for listing in listings:
            if processed >= effective_limit:
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

            if dedupe_company_title and has_duplicate_company_title(listing.company, listing.title):
                skipped_count += 1
                results.append(
                    {
                        "job_id": listing.job_id,
                        "title": listing.title,
                        "company": listing.company,
                        "status": "skipped",
                        "reason": "duplicate_company_title",
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

            if match_score < resolved_min_score:
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
                application.error_message = (
                    f"Match score {match_score} below minimum {resolved_min_score}"
                )
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
            "limit": effective_limit,
            "min_match_score": resolved_min_score,
            "daily_cap": resolved_daily_cap,
            "tailored_today_before_run": already_today,
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
    max_custom_questions: Optional[int] = None,
    use_llm: Optional[bool] = None,
    linkedin_email: Optional[str] = None,
    linkedin_password: Optional[str] = None,
    headless: Optional[bool] = None,
    close_linkedin_session: bool = True,
) -> Dict[str, Any]:
    """Run LinkedIn Easy Apply for a queued application."""
    resolved_max_questions = (
        max_custom_questions
        if max_custom_questions is not None
        else DEFAULT_MAX_CUSTOM_QUESTIONS
    )
    resolved_use_llm = USE_LLM_SCREENING if use_llm is None else use_llm
    profile = _load_profile_defaults()
    missing = validate_profile_for_apply(profile)
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

    if missing:
        logger.warning("Application profile missing recommended fields: %s", missing)

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
            profile=profile,
            job_title=application.title,
            require_approval=require_approval,
            max_custom_questions=resolved_max_questions,
            use_llm=resolved_use_llm,
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
        "tailored_today": count_tailored_today(),
        "daily_cap": DAILY_TAILOR_CAP,
        "applications": [app.to_dict() for app in applications],
    }


def export_queue_csv(
    output_path: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Export the application queue to CSV."""
    path = export_applications_csv(output_path=output_path, status=status)
    return {
        "success": True,
        "file_path": str(path),
        "message": f"Exported queue to {path}",
    }


def check_pipeline_setup() -> Dict[str, Any]:
    """Validate environment and profile before running the pipeline."""
    issues: List[str] = []
    warnings: List[str] = []

    if not os.getenv("RESUMEUP_EMAIL") and not os.getenv("RESUMEUP_PASSWORD"):
        warnings.append("RESUMEUP_EMAIL/PASSWORD not set — manual ResumeUp login may be required")

    if not os.getenv("LINKEDIN_EMAIL") and not os.getenv("LINKEDIN_PASSWORD"):
        warnings.append("LINKEDIN_EMAIL/PASSWORD not set — manual LinkedIn login may be required")

    if not os.getenv("PROFILE_SKILLS"):
        warnings.append("PROFILE_SKILLS not set — match scoring will accept all jobs")

    profile = load_application_profile()
    missing = validate_profile_for_apply(profile)
    if missing:
        warnings.append(f"Application profile missing: {', '.join(missing)}")

    if not os.getenv("OPENAI_API_KEY"):
        warnings.append("OPENAI_API_KEY not set — LLM screening fallback disabled")

    profile_path = os.getenv("APPLICATION_PROFILE_PATH", "examples/application_profile.json")
    if not Path(os.path.expanduser(profile_path)).exists():
        issues.append(f"Application profile not found: {profile_path}")

    return {
        "success": len(issues) == 0,
        "ready": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "defaults": {
            "min_match_score": DEFAULT_MIN_MATCH_SCORE,
            "search_limit": DEFAULT_SEARCH_LIMIT,
            "daily_cap": DAILY_TAILOR_CAP,
            "max_custom_questions": DEFAULT_MAX_CUSTOM_QUESTIONS,
        },
    }
