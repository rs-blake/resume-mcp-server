"""Parse structured resume text into sections for editor updates."""

from __future__ import annotations

import re
from typing import Dict

SECTION_HEADERS = (
    "SUMMARY",
    "SKILLS",
    "WORK EXPERIENCE",
    "EXPERIENCE",
    "EDUCATION",
    "CERTIFICATIONS",
    "PROJECTS",
)

HEADER_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(header) for header in SECTION_HEADERS) + r")\s*:?\s*$",
    re.I | re.M,
)


def parse_resume_sections(text: str) -> Dict[str, str]:
    """Split resume text into section name -> content mappings."""
    sections: Dict[str, str] = {}
    matches = list(HEADER_PATTERN.finditer(text))
    if not matches:
        return {"Summary": text.strip()} if text.strip() else {}

    for index, match in enumerate(matches):
        name = match.group(1).strip().title()
        if name == "Experience":
            name = "Work Experience"

        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            sections[name] = content

    return sections


def merge_sections(base: Dict[str, str], updates: Dict[str, str]) -> Dict[str, str]:
    """Merge update sections into a base section map."""
    merged = dict(base)
    merged.update({key: value for key, value in updates.items() if value.strip()})
    return merged
