"""Unit tests for LinkedIn job search helpers."""

from linkedin_job_search import build_search_url, extract_job_id_from_url


def test_build_search_url_easy_apply():
    url = build_search_url("security architect", location="Remote", easy_apply_only=True)
    assert "keywords=security+architect" in url
    assert "f_AL=true" in url
    assert "location=Remote" in url


def test_build_search_url_remote_filter():
    url = build_search_url("python developer", remote_only=True, easy_apply_only=False)
    assert "f_WT=2" in url
    assert "f_AL" not in url


def test_extract_job_id_from_view_url():
    job_id = extract_job_id_from_url("https://www.linkedin.com/jobs/view/1234567890/")
    assert job_id == "1234567890"


def test_extract_job_id_from_search_url():
    job_id = extract_job_id_from_url(
        "https://www.linkedin.com/jobs/search/?currentJobId=9876543210"
    )
    assert job_id == "9876543210"
