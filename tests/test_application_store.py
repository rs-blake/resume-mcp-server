"""Unit tests for application_store."""

import json
from pathlib import Path

from application_store import (
    count_tailored_today,
    create_application,
    export_applications_csv,
    get_application,
    has_applied_to_job,
    has_duplicate_company_title,
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


def test_has_duplicate_company_title(tmp_path: Path):
    store = tmp_path / "apps.json"
    create_application(
        job_id="1",
        job_url="https://example.com/1",
        title="Software Engineer",
        company="Acme Corp",
        store_path=store,
    )
    assert has_duplicate_company_title("Acme Corp", "Software Engineer", store_path=store)
    assert not has_duplicate_company_title("Acme Corp", "Staff Engineer", store_path=store)


def test_export_applications_csv(tmp_path: Path):
    store = tmp_path / "apps.json"
    create_application(
        job_id="77",
        job_url="https://example.com/77",
        title="Engineer",
        company="Beta",
        status="tailored",
        store_path=store,
    )
    csv_path = export_applications_csv(
        output_path=str(tmp_path / "queue.csv"),
        store_path=store,
    )
    content = csv_path.read_text(encoding="utf-8")
    assert "application_id" in content
    assert "Beta" in content


def test_count_tailored_today(tmp_path: Path):
    store = tmp_path / "apps.json"
    create_application(
        job_id="9",
        job_url="https://example.com/9",
        status="tailored",
        store_path=store,
    )
    assert count_tailored_today(store_path=store) >= 1
