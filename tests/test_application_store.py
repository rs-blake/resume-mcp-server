"""Unit tests for application_store."""

import json
from pathlib import Path

from application_store import (
    create_application,
    get_application,
    has_applied_to_job,
    list_applications,
    update_application_status,
)


def test_create_and_get_application(tmp_path: Path):
    store = tmp_path / "apps.json"
    application = create_application(
        job_id="12345",
        job_url="https://www.linkedin.com/jobs/view/12345",
        title="Engineer",
        company="Acme",
        store_path=store,
    )

    fetched = get_application(application_id=application.application_id, store_path=store)
    assert fetched is not None
    assert fetched.job_id == "12345"
    assert fetched.status == "discovered"


def test_update_application_status(tmp_path: Path):
    store = tmp_path / "apps.json"
    application = create_application(
        job_id="999",
        job_url="https://www.linkedin.com/jobs/view/999",
        store_path=store,
    )

    updated = update_application_status(
        application.application_id,
        "tailored",
        resume_score=96,
        pdf_path="/tmp/resume.pdf",
        store_path=store,
    )
    assert updated is not None
    assert updated.status == "tailored"
    assert updated.resume_score == 96
    assert updated.pdf_path == "/tmp/resume.pdf"


def test_has_applied_to_job(tmp_path: Path):
    store = tmp_path / "apps.json"
    create_application(job_id="555", job_url="https://example.com/555", store_path=store)
    assert has_applied_to_job("555", store_path=store) is True
    assert has_applied_to_job("404", store_path=store) is False


def test_list_applications_filter_by_status(tmp_path: Path):
    store = tmp_path / "apps.json"
    create_application(job_id="1", job_url="https://example.com/1", status="tailored", store_path=store)
    create_application(job_id="2", job_url="https://example.com/2", status="skipped", store_path=store)

    tailored = list_applications(status="tailored", store_path=store)
    assert len(tailored) == 1
    assert tailored[0].job_id == "1"

    payload = json.loads(store.read_text(encoding="utf-8"))
    assert "applications" in payload
