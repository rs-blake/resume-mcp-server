"""Unit tests for screening_question_handler."""

from screening_question_handler import _keyword_match, resolve_screening_answer


PROFILE = {
    "work_authorization": "Yes",
    "requires_sponsorship": "No",
    "years_experience": "5",
    "salary_expectation": "150000",
    "screening_answers": {
        "authorized to work in the united states": "Yes",
        "require visa sponsorship": "No",
        "expected salary": "150000",
    },
    "default_text_answers": {
        "why are you interested": "Strong fit for my background.",
    },
}


def test_keyword_match_work_authorization():
    answer = _keyword_match("Are you legally authorized to work in the United States?", PROFILE)
    assert answer == "Yes"


def test_keyword_match_sponsorship():
    answer = _keyword_match("Will you now or in the future require visa sponsorship?", PROFILE)
    assert answer == "No"


def test_keyword_match_salary():
    answer = _keyword_match("What is your expected salary?", PROFILE)
    assert answer == "150000"


def test_resolve_without_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    answer = resolve_screening_answer(
        "Why are you interested in this role?",
        profile=PROFILE,
        use_llm=False,
    )
    assert "Strong fit" in answer
