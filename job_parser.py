"""Job description parsing utilities."""

import re
import logging
from typing import List, Optional

from models import JobRequirements

logger = logging.getLogger(__name__)

# Common job titles and variations
JOB_TITLE_PATTERNS = [
    r"(?:job\s+)?title\s*:?\s*(.+?)(?:\n|$)",
    r"^(.+?)\s+(?:Position|Role|Job)$",
    r"(?:We're hiring|We are hiring|Open position)\s+(?:for\s+)?(?:a\s+)?(.+?)(?:\.|$)",
]

# Common sections in job descriptions
SECTION_MARKERS = {
    "responsibilities": [
        r"(?:primary\s+)?(?:duties\s+and\s+)?responsibilities",
        r"what you'll do",
        r"day-to-day",
        r"you will",
    ],
    "requirements": [
        r"(?:key\s+)?requirements",
        r"qualifications",
        r"must have",
        r"required",
    ],
    "nice_to_have": [
        r"(?:nice\s+)?to have",
        r"preferred",
        r"bonus",
        r"advantage",
    ],
    "benefits": [
        r"benefits",
        r"compensation",
        r"perks",
    ],
}

# Common skills and technologies to look for
TECH_KEYWORDS = [
    # Languages
    r"\bpython\b", r"\bjava\b", r"\bc\+\+\b", r"\bc#\b", r"\bjavascript\b",
    r"\btypescript\b", r"\bgo\b", r"\brust\b", r"\bphp\b", r"\bruby\b",
    
    # Cloud & Infrastructure
    r"\baws\b", r"\bazure\b", r"\bgcp\b", r"\bkubernetes\b", r"\bdocker\b",
    r"\bterraform\b", r"\bansible\b", r"\bcloud\b",
    
    # Security
    r"\bsecurity\b", r"\bcybersecurity\b", r"\bsiem\b", r"\bsoar\b",
    r"\bedr\b", r"\bxdr\b", r"\bfirewall\b", r"\bvpn\b", r"\biam\b",
    r"\bztna\b", r"\bad\b", r"\blap\b", r"\bos\s+hardening\b",
    
    # Databases
    r"\bsql\b", r"\bmysql\b", r"\bpostgres\b", r"\bmongodb\b", r"\bredis\b",
    
    # DevOps & CI/CD
    r"\bcicd\b", r"\bci/cd\b", r"\bjenkins\b", r"\bgithub\b", r"\bgitlab\b",
    
    # Other common tech
    r"\bapi\b", r"\brest\b", r"\bgrpc\b", r"\bmicroservices\b",
    r"\bcontainers\b", r"\blinux\b", r"\bwindows\b",
]

SKILL_PATTERNS = [
    r"(?:skills?|expertise|knowledge|experience|proficient)(?:\s+(?:in|with))?\s*:?\s*([^:\n]+)",
    r"\b(?:strong|excellent|advanced|expert)\s+(?:in|with)\s+([^,\n]+)",
]


def extract_job_title(text: str) -> Optional[str]:
    """Extract job title from text.
    
    Args:
        text: Job description text
        
    Returns:
        Extracted job title or None
    """
    text_lower = text.lower()
    
    # Look for common title patterns
    for pattern in JOB_TITLE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Clean up the title
            title = re.sub(r'\s+', ' ', title)  # Normalize whitespace
            if len(title) < 100 and len(title) > 2:  # Sanity check
                logger.debug(f"Extracted job title: {title}")
                return title
    
    # Default to first non-empty line if it looks like a title
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if 5 < len(candidate) < 100 and not any(c in candidate for c in ['?', ':']):
            return candidate
        break
    
    return None


def extract_company(text: str) -> Optional[str]:
    """Extract company name from text.
    
    Args:
        text: Job description text
        
    Returns:
        Extracted company name or None
    """
    patterns = [
        r"(?:company|employer|organization)\s*:?\s*([^\n,]+)",
        r"at\s+([A-Z][A-Za-z\s&]+?)(?:\s+(?:is\s+)?(?:hiring|recruiting)|$)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            if len(company) < 100:
                logger.debug(f"Extracted company: {company}")
                return company
    
    return None


def extract_skills_from_text(text: str) -> List[str]:
    """Extract technical skills and keywords from job description.
    
    Args:
        text: Job description text
        
    Returns:
        List of extracted skills
    """
    text_lower = text.lower()
    found_skills = set()
    
    # Find skills using keyword patterns
    for pattern in TECH_KEYWORDS:
        if re.search(pattern, text_lower):
            # Extract the keyword
            match = re.search(pattern, text_lower)
            if match:
                skill = match.group(0)
                found_skills.add(skill.upper() if len(skill) < 5 else skill.title())
    
    # Find skills mentioned in skill sections
    for skill_pattern in SKILL_PATTERNS:
        matches = re.findall(skill_pattern, text, re.IGNORECASE)
        for match in matches:
            # Split by comma or 'and' and clean up
            skills = re.split(r',|and', match)
            for skill in skills:
                skill = skill.strip()
                if 2 < len(skill) < 50:
                    found_skills.add(skill)
    
    result = sorted(list(found_skills))
    logger.debug(f"Extracted {len(result)} skills: {result[:10]}")
    return result


def extract_section(text: str, section_name: str) -> str:
    """Extract a specific section from job description.
    
    Args:
        text: Job description text
        section_name: Name of section to extract (requirements, responsibilities, etc.)
        
    Returns:
        Extracted section text or empty string
    """
    if section_name not in SECTION_MARKERS:
        return ""
    
    patterns = SECTION_MARKERS[section_name]
    
    # Find the section start
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            section_start = match.end()
            
            # Find where this section ends (next heading or another section)
            remaining_text = text[section_start:]
            next_section = re.search(r'\n\s*[A-Z][A-Za-z\s]+:\s*\n', remaining_text)
            
            if next_section:
                section_end = section_start + next_section.start()
            else:
                section_end = len(text)
            
            section_text = text[section_start:section_end].strip()
            return section_text
    
    return ""


def parse_requirements_list(text: str) -> List[str]:
    """Parse requirements from text, handling bullet points and numbered lists.
    
    Args:
        text: Requirements section text
        
    Returns:
        List of individual requirements
    """
    requirements = []
    
    # Split by bullet points, dashes, or numbers
    lines = re.split(r'[\n•\-*]|\d+\.\s+', text)
    
    for line in lines:
        line = line.strip()
        # Remove leading/trailing markers
        line = re.sub(r'^[-•*\d.]\s+', '', line)
        
        if len(line) > 5 and not line.endswith(':'):
            requirements.append(line)
    
    return requirements


def parse_job_description(job_text: str) -> JobRequirements:
    """Parse a job description into structured components.
    
    Args:
        job_text: Full job description text
        
    Returns:
        JobRequirements object with extracted data
    """
    logger.info("Parsing job description")
    
    # Extract main fields
    title = extract_job_title(job_text) or "Job Position"
    company = extract_company(job_text)
    
    # Extract skills
    key_skills = extract_skills_from_text(job_text)
    
    # Extract sections
    requirements_text = extract_section(job_text, "requirements")
    if not requirements_text:
        requirements_text = extract_section(job_text, "responsibilities")
    
    requirements = parse_requirements_list(requirements_text)
    if not requirements:
        requirements = parse_requirements_list(job_text)
    
    nice_to_haves_text = extract_section(job_text, "nice_to_have")
    nice_to_haves = parse_requirements_list(nice_to_haves_text)
    
    result = JobRequirements(
        title=title,
        company=company,
        key_skills=key_skills,
        requirements=requirements[:10],  # Limit to top 10
        nice_to_haves=nice_to_haves[:5],  # Limit to top 5
        full_text=job_text,
    )
    
    logger.info(f"Parsed job: {result.title} at {result.company}")
    logger.debug(f"Found {len(result.key_skills)} skills and {len(result.requirements)} requirements")
    
    return result
