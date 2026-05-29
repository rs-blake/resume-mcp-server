"""Unit tests for utility helpers."""

from utils import extract_resume_id_from_url, find_resume_score


class FakePage:
    def __init__(self, text: str):
        self._text = text

    def inner_text(self, _selector: str) -> str:
        return self._text


def test_extract_resume_id_from_url():
    url = "https://app.resumeup.ai/resume-builder/abc12345-6789-4def-9012-3456789abcde"
    assert extract_resume_id_from_url(url) == "abc12345-6789-4def-9012-3456789abcde"


def test_find_resume_score_from_fraction():
    page = FakePage("Resume score\n79/100\nRe-analyse")
    assert find_resume_score(page) == 79


def test_find_resume_score_from_percentage():
    page = FakePage("My Resumes\nResume Score: 100%\nUpdated today")
    assert find_resume_score(page) == 100


def test_find_resume_score_missing():
    page = FakePage("Welcome to resumeup.ai")
    assert find_resume_score(page) is None
