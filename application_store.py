"""Persistent storage for job applications and review queue."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import JobApplication

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = Path(
    os.path.expanduser(os.getenv("APPLICATION_STORE_PATH", "~/.resumeup_automation/applications.json"))
)


def _default_store_path() -> Path:
    path = DEFAULT_STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_raw(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    store_path = path or _default_store_path()
    if not store_path.exists():
        return []

    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read application store: %s", exc)
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("applications", [])
    return []


def _save_raw(records: List[Dict[str, Any]], path: Optional[Path] = None) -> None:
    store_path = path or _default_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"applications": records, "updated_at": time.time()}
    store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _to_application(record: Dict[str, Any]) -> JobApplication:
    return JobApplication(
        application_id=record["application_id"],
        job_id=record["job_id"],
        job_url=record["job_url"],
        title=record.get("title", ""),
        company=record.get("company", ""),
        location=record.get("location", ""),
        status=record.get("status", "discovered"),
        match_score=record.get("match_score"),
        resume_score=record.get("resume_score"),
        pdf_path=record.get("pdf_path"),
        job_description_path=record.get("job_description_path"),
        easy_apply=bool(record.get("easy_apply", False)),
        error_message=record.get("error_message"),
        created_at=float(record.get("created_at", time.time())),
        updated_at=float(record.get("updated_at", time.time())),
    )


def _to_dict(application: JobApplication) -> Dict[str, Any]:
    return {
        "application_id": application.application_id,
        "job_id": application.job_id,
        "job_url": application.job_url,
        "title": application.title,
        "company": application.company,
        "location": application.location,
        "status": application.status,
        "match_score": application.match_score,
        "resume_score": application.resume_score,
        "pdf_path": application.pdf_path,
        "job_description_path": application.job_description_path,
        "easy_apply": application.easy_apply,
        "error_message": application.error_message,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
    }


def list_applications(
    status: Optional[str] = None,
    limit: Optional[int] = None,
    store_path: Optional[Path] = None,
) -> List[JobApplication]:
    """Return applications, optionally filtered by status."""
    records = _load_raw(store_path)
    applications = [_to_application(record) for record in records]

    if status:
        applications = [app for app in applications if app.status == status]

    applications.sort(key=lambda app: app.updated_at, reverse=True)
    if limit is not None:
        applications = applications[:limit]
    return applications


def get_application(
    application_id: Optional[str] = None,
    job_id: Optional[str] = None,
    store_path: Optional[Path] = None,
) -> Optional[JobApplication]:
    """Fetch a single application by ID or LinkedIn job ID."""
    for application in list_applications(store_path=store_path):
        if application_id and application.application_id == application_id:
            return application
        if job_id and application.job_id == job_id:
            return application
    return None


def has_applied_to_job(job_id: str, store_path: Optional[Path] = None) -> bool:
    """Return True if this job ID already has a non-skipped record."""
    application = get_application(job_id=job_id, store_path=store_path)
    if application is None:
        return False
    return application.status not in {"skipped"}


def save_application(application: JobApplication, store_path: Optional[Path] = None) -> JobApplication:
    """Insert or update an application record."""
    path = store_path or _default_store_path()
    records = _load_raw(path)

    application.updated_at = time.time()
    payload = _to_dict(application)

    updated = False
    for index, record in enumerate(records):
        if record.get("application_id") == application.application_id or record.get("job_id") == application.job_id:
            records[index] = payload
            updated = True
            break

    if not updated:
        records.append(payload)

    _save_raw(records, path)
    return application


def create_application(
    job_id: str,
    job_url: str,
    title: str = "",
    company: str = "",
    location: str = "",
    easy_apply: bool = False,
    status: str = "discovered",
    store_path: Optional[Path] = None,
) -> JobApplication:
    """Create a new application record."""
    now = time.time()
    application = JobApplication(
        application_id=str(uuid.uuid4()),
        job_id=job_id,
        job_url=job_url,
        title=title,
        company=company,
        location=location,
        status=status,
        easy_apply=easy_apply,
        created_at=now,
        updated_at=now,
    )
    return save_application(application, store_path=store_path)


def update_application_status(
    application_id: str,
    status: str,
    *,
    resume_score: Optional[int] = None,
    pdf_path: Optional[str] = None,
    job_description_path: Optional[str] = None,
    match_score: Optional[float] = None,
    error_message: Optional[str] = None,
    store_path: Optional[Path] = None,
) -> Optional[JobApplication]:
    """Update fields on an existing application."""
    application = get_application(application_id=application_id, store_path=store_path)
    if application is None:
        return None

    application.status = status
    if resume_score is not None:
        application.resume_score = resume_score
    if pdf_path is not None:
        application.pdf_path = pdf_path
    if job_description_path is not None:
        application.job_description_path = job_description_path
    if match_score is not None:
        application.match_score = match_score
    if error_message is not None:
        application.error_message = error_message

    return save_application(application, store_path=store_path)
