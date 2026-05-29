"""Answer LinkedIn Easy Apply screening questions from profile rules or optional LLM."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from application_profile import load_application_profile, profile_as_flat_strings

logger = logging.getLogger(__name__)

OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _keyword_match(question: str, profile: Dict[str, Any]) -> Optional[str]:
    """Match question text against screening_answers and flat profile fields."""
    normalized_question = _normalize(question)
    flat = profile_as_flat_strings(profile)

    screening = profile.get("screening_answers", {})
    if isinstance(screening, dict):
        for pattern, answer in screening.items():
            if _normalize(pattern) in normalized_question or normalized_question in _normalize(pattern):
                return str(answer)

    for key, value in flat.items():
        key_norm = _normalize(key.replace("_", " "))
        if key_norm in normalized_question:
            return value

    keyword_rules = [
        (r"authorized to work|legally authorized", "work_authorization"),
        (r"sponsorship|visa", "requires_sponsorship"),
        (r"years.{0,20}experience", "years_experience"),
        (r"salary|compensation|pay expectation", "salary_expectation"),
        (r"relocate", "willing_to_relocate"),
        (r"clearance", "has_security_clearance"),
        (r"notice period|start date|when can you start", "notice_period_days"),
    ]
    for pattern, profile_key in keyword_rules:
        if re.search(pattern, normalized_question):
            value = profile.get(profile_key) or flat.get(profile_key)
            if value:
                return str(value)

    text_defaults = profile.get("default_text_answers", {})
    if isinstance(text_defaults, dict):
        for pattern, answer in text_defaults.items():
            if _normalize(pattern) in normalized_question:
                return str(answer)

    return None


def _llm_answer(question: str, profile: Dict[str, Any], job_title: str = "") -> Optional[str]:
    """Optional OpenAI-compatible LLM fallback for unmatched questions."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    system_prompt = (
        "You answer LinkedIn job application screening questions concisely. "
        "Use only facts from the candidate profile JSON. "
        "For yes/no questions reply with Yes or No only. "
        "For numeric questions reply with digits only when appropriate. "
        "Keep text answers under 300 characters."
    )
    user_prompt = json.dumps(
        {
            "question": question,
            "job_title": job_title,
            "profile": profile,
        },
        indent=2,
    )

    try:
        response = httpx.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 120,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()
        return content or None
    except Exception as exc:
        logger.warning("LLM screening answer failed: %s", exc)
        return None


def resolve_screening_answer(
    question: str,
    profile: Optional[Dict[str, Any]] = None,
    job_title: str = "",
    use_llm: bool = True,
) -> Optional[str]:
    """Resolve an answer for a screening question."""
    profile = profile or load_application_profile()
    answer = _keyword_match(question, profile)
    if answer:
        return answer
    if use_llm and os.getenv("OPENAI_API_KEY"):
        return _llm_answer(question, profile, job_title=job_title)
    return None


def extract_visible_questions(page) -> List[Dict[str, str]]:
    """Extract question labels from the current Easy Apply step."""
    questions: List[Dict[str, str]] = []

    for locator in [
        page.locator("label"),
        page.locator('[data-test-form-element] label'),
        page.locator("legend"),
    ]:
        count = min(locator.count(), 30)
        for index in range(count):
            try:
                text = locator.nth(index).inner_text(timeout=1000).strip()
            except Exception:
                continue
            if not text or len(text) < 4:
                continue
            normalized = _normalize(text)
            if normalized in {q["label"] for q in questions}:
                continue
            questions.append({"label": normalized, "raw": text})
    return questions


def answer_screening_questions_on_page(
    page,
    profile: Optional[Dict[str, Any]] = None,
    job_title: str = "",
    use_llm: bool = True,
) -> int:
    """Fill visible screening fields using profile rules and optional LLM."""
    profile = profile or load_application_profile()
    answered = 0

    questions = extract_visible_questions(page)
    for question in questions:
        answer = resolve_screening_answer(
            question["raw"],
            profile=profile,
            job_title=job_title,
            use_llm=use_llm,
        )
        if not answer:
            continue

        raw = question["raw"]
        filled = False

        for getter, action in [
            (lambda: page.get_by_label(re.compile(re.escape(raw[:80]), re.I)), "fill"),
            (lambda: page.get_by_label(re.compile(re.escape(question["label"][:80]), re.I)), "fill"),
        ]:
            field = getter()
            if field.count() > 0:
                try:
                    if action == "fill":
                        field.first.fill(answer, timeout=2000)
                    answered += 1
                    filled = True
                    break
                except Exception:
                    pass

        if filled:
            continue

        radio = page.get_by_role("radio", name=re.compile(re.escape(answer), re.I))
        if radio.count() > 0:
            try:
                radio.first.click(timeout=2000)
                answered += 1
                continue
            except Exception:
                pass

        option = page.get_by_role("option", name=re.compile(re.escape(answer), re.I))
        if option.count() > 0:
            try:
                option.first.click(timeout=2000)
                answered += 1
            except Exception:
                pass

    return answered
