"""
src/parsers/resume_parser.py
----------------------------
WHY THIS FILE EXISTS
----------------------------
A resume PDF is unstructured text. There is no guaranteed layout, no
column headers, no schema. This module uses pdfplumber to extract raw text
from every page, then uses regular expressions to locate fields like email,
phone, LinkedIn URL, and skills from that text.

WHY REGEX FOR PARSING?
  For truly unstructured text the two main approaches are:
  1. Regex — fast, deterministic, easy to debug, but brittle to new layouts.
  2. LLM/NLP extraction — flexible but adds heavy dependencies and cost.
  For this internship project, regex is the right choice: it is transparent,
  interview-friendly, and teaches important skills.

PIPELINE CONNECTION
-------------------
  main.py  →  resume_parser.parse(path)  →  CandidateRecord (source="Resume")
  The CandidateRecord goes straight to the Merger.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pdfplumber

from src.models.schema import CandidateRecord, LocationData, LinksData, ExperienceEntry
from src.parsers.csv_parser import ParseError   # reuse the same exception type
from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Compiled regular expressions
# ---------------------------------------------------------------------------
# WHY compile upfront:
#   re.compile() converts the pattern string into a compiled regex object.
#   If parse() is called many times (e.g. batch processing) this saves
#   re-compiling the same pattern on every call. It also keeps patterns
#   named and documented in one place.
# ---------------------------------------------------------------------------

# Email — standard RFC 5321-ish pattern
_RE_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Phone — common formats: +1 (415) 555-2671, 415-555-2671, (415)555.2671
_RE_PHONE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{4}"
)

# LinkedIn profile URL
_RE_LINKEDIN = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+"
)

# GitHub profile URL
_RE_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+"
)

# Portfolio / personal website — very loose, catch http(s):// URLs that are
# not LinkedIn or GitHub
_RE_PORTFOLIO = re.compile(
    r"https?://(?!(?:www\.)?(?:linkedin|github)\.com)[\w\-./]+"
)

# Date ranges in experience sections, e.g.:
#   "Jan 2020 – Present", "2019 - 2022", "March 2018 – June 2021"
_RE_DATE_RANGE = re.compile(
    r"(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*[-–—]\s*"
    r"(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
    r"|\d{4}|[Pp]resent|[Cc]urrent)",
    re.IGNORECASE,
)

# Skills section header — detects a line that introduces a skills list
_RE_SKILLS_HEADER = re.compile(
    r"^\s*(?:technical\s+)?skills?(?:\s*[:&/]|$)", re.IGNORECASE
)

# Common skill delimiters: comma, pipe, bullet, newline
_RE_SKILL_SPLIT = re.compile(r"[,|•·\n]+")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(pdf_path: str) -> CandidateRecord:
    """
    Extract candidate data from a resume PDF and return a CandidateRecord.

    The extraction is best-effort: fields that cannot be located are set to
    None/[] rather than raising exceptions.

    Args:
        pdf_path: Path to the resume PDF file.

    Returns:
        CandidateRecord with source="Resume".

    Raises:
        ParseError: If the file cannot be opened or pdfplumber fails.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise ParseError(f"Resume PDF not found: {pdf_path}")

    logger.info("Parsing resume PDF: %s", pdf_path)

    try:
        # CONCEPT — pdfplumber.open():
        #   pdfplumber is a library that extracts text from PDFs while
        #   preserving layout information. We iterate over every page and
        #   concatenate the text with newline separators.
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

        if not pages_text:
            logger.warning("No extractable text found in PDF: %s", pdf_path)
            full_text = ""
        else:
            full_text = "\n".join(pages_text)

        logger.debug("Extracted %d characters from PDF", len(full_text))

    except Exception as exc:
        raise ParseError(f"Failed to open PDF {pdf_path}: {exc}") from exc

    # --- Try AI extraction first, fall back to regex ---
    from src.parsers import ai_resume_parser

    if ai_resume_parser.is_available() and full_text:
        ai_record = ai_resume_parser.extract(full_text)
        if ai_record:
            logger.info("Using AI-extracted resume record.")
            return ai_record
        logger.warning("AI extraction failed or returned nothing — falling back to regex parser.")

    # --- Regex fallback: extract each field from the raw text ---
    logger.info("Using regex-based resume extraction.")
    emails = _extract_emails(full_text)
    phones = _extract_phones(full_text)
    linkedin = _extract_linkedin(full_text)
    github = _extract_github(full_text)
    portfolio = _extract_portfolio(full_text)
    skills = _extract_skills(full_text)
    experience, years_exp = _extract_experience(full_text)
    full_name = _extract_name(full_text)
    headline = _extract_headline(full_text)
    location = _extract_location(full_text)

    record = CandidateRecord(
        source="Resume",
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=LinksData(
            linkedin=linkedin,
            github=github,
            portfolio=portfolio,
        ),
        headline=headline,
        years_experience=years_exp,
        skills=skills,
        experience=experience,
    )

    logger.info(
        "Resume parsed — name=%r, emails=%d, phones=%d, skills=%d, experience_entries=%d",
        full_name,
        len(emails),
        len(phones),
        len(skills),
        len(experience),
    )

    return record


# ---------------------------------------------------------------------------
# Private extraction helpers
# ---------------------------------------------------------------------------
# Each helper focuses on one field. They accept the full text string and
# return the extracted value(s). If nothing is found, they return None or [].

def _extract_emails(text: str) -> list[str]:
    """Find all email addresses in the text."""
    return list(dict.fromkeys(_RE_EMAIL.findall(text)))   # deduplicate, preserve order


def _extract_phones(text: str) -> list[str]:
    """Find all phone-like strings in the text."""
    raw_phones = _RE_PHONE.findall(text)
    # Filter out very short matches that are likely not phone numbers
    return list(dict.fromkeys(p.strip() for p in raw_phones if len(p.replace(" ", "").replace("-", "")) >= 7))


def _extract_linkedin(text: str) -> Optional[str]:
    """Extract the first LinkedIn profile URL found."""
    match = _RE_LINKEDIN.search(text)
    return match.group(0) if match else None


def _extract_github(text: str) -> Optional[str]:
    """Extract the first GitHub profile URL found."""
    match = _RE_GITHUB.search(text)
    return match.group(0) if match else None


def _extract_portfolio(text: str) -> Optional[str]:
    """Extract the first non-LinkedIn, non-GitHub URL found."""
    match = _RE_PORTFOLIO.search(text)
    return match.group(0) if match else None


def _extract_name(text: str) -> Optional[str]:
    """
    Heuristic: the candidate's name is usually the first non-empty line
    of the resume (before contact details).

    This is imperfect but works for the vast majority of resume formats.
    A more robust approach would use NLP named-entity recognition.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return None

    first_line = lines[0]

    # Reject if it looks like a URL, email, phone, or section header
    if any(pat.search(first_line) for pat in [_RE_EMAIL, _RE_PHONE, _RE_LINKEDIN]):
        return None

    # A name should be 2–5 words, all alphabetic with possible hyphens
    words = first_line.split()
    if 2 <= len(words) <= 5 and all(re.match(r"[A-Za-z\-']+$", w) for w in words):
        return first_line

    return None


def _extract_headline(text: str) -> Optional[str]:
    """
    Heuristic: the headline/summary is typically the second non-empty line
    after the name, or the line directly below the name that is not contact
    info.
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return None

    candidate_lines = lines[1:4]  # check lines 2-4
    for line in candidate_lines:
        # Skip lines that are clearly contact info
        if _RE_EMAIL.search(line) or _RE_PHONE.search(line) or _RE_LINKEDIN.search(line):
            continue
        # Skip very short lines (likely formatting artifacts)
        if len(line) < 10:
            continue
        # A reasonable headline is usually 5–20 words
        words = line.split()
        if 5 <= len(words) <= 25:
            return line

    return None


def _extract_location(text: str) -> LocationData:
    """
    Heuristic location extraction. Looks for patterns like:
      "New York, NY"  /  "London, UK"  /  "San Francisco, CA, USA"

    Returns an empty LocationData if nothing is found.
    """
    # Pattern: City, Region / City, Country / City, Region, Country
    pattern = re.compile(
        r"\b([A-Z][a-zA-Z\s]+),\s*([A-Z]{2,3}|[A-Z][a-zA-Z\s]+?)(?:,\s*([A-Z]{2,3}|[A-Z][a-zA-Z]+))?\b"
    )
    match = pattern.search(text)
    if not match:
        return LocationData()

    city = safe_strip(match.group(1))
    region_or_country = safe_strip(match.group(2))
    extra = safe_strip(match.group(3))

    if extra:
        # City, Region, Country
        return LocationData(city=city, region=region_or_country, country=extra)

    # Decide if the second group looks like a 2-letter state/country code
    if region_or_country and len(region_or_country) == 2 and region_or_country.isupper():
        return LocationData(city=city, region=region_or_country)

    return LocationData(city=city, country=region_or_country)


def _extract_skills(text: str) -> list[str]:
    """
    Locate a 'Skills' section in the text and extract items from it.

    Strategy:
    1. Find the line that starts the skills section.
    2. Collect lines until the next section header or end of text.
    3. Split on common delimiters (comma, pipe, bullet).
    """
    lines = text.split("\n")
    skills_lines: list[str] = []
    in_skills = False

    for line in lines:
        if _RE_SKILLS_HEADER.match(line):
            in_skills = True
            # The skills may start on the same line after the header
            after_header = re.sub(r"^\s*(?:technical\s+)?skills?\s*[:&/]?\s*", "", line, flags=re.IGNORECASE)
            if after_header.strip():
                skills_lines.append(after_header)
            continue

        if in_skills:
            # Stop when we hit the next section header (all-caps line or
            # a known section keyword)
            if _is_section_header(line):
                break
            skills_lines.append(line)

    combined = " ".join(skills_lines)
    raw_skills = [s.strip() for s in _RE_SKILL_SPLIT.split(combined) if s.strip()]
    # Filter out very long strings (likely sentences, not skill names)
    return [s for s in raw_skills if len(s) <= 40]


def _extract_experience(text: str) -> tuple[list[ExperienceEntry], Optional[int]]:
    """
    Extract work experience entries and estimate total years of experience.

    Returns:
        Tuple of (list[ExperienceEntry], years_experience_int_or_None)
    """
    entries: list[ExperienceEntry] = []

    # Find all date ranges in the text
    date_ranges = list(_RE_DATE_RANGE.finditer(text))

    for match in date_ranges:
        start_str = safe_strip(match.group("start"))
        end_str = safe_strip(match.group("end"))

        # Try to grab the surrounding context as title/company (30 chars before)
        context_start = max(0, match.start() - 120)
        context = text[context_start: match.start()].strip()
        context_lines = [l.strip() for l in context.split("\n") if l.strip()]

        title = context_lines[-1] if context_lines else None
        company = context_lines[-2] if len(context_lines) >= 2 else None

        entries.append(ExperienceEntry(
            title=title,
            company=company,
            start_date=start_str,
            end_date=end_str,
        ))

    # Estimate total years from the span of all date ranges found
    years_exp = _estimate_years(date_ranges, text)

    return entries, years_exp


def _estimate_years(date_matches: list, text: str) -> Optional[int]:
    """
    Estimate total years of professional experience from date ranges.

    Uses the earliest start year and the latest end year (or current year
    for "Present").
    """
    import datetime

    if not date_matches:
        # Fallback: look for "X years of experience" pattern
        pattern = re.compile(r"(\d+)\+?\s+years?\s+(?:of\s+)?experience", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return int(match.group(1))
        return None

    current_year = datetime.datetime.now().year
    years: list[int] = []

    for match in date_matches:
        for group_name in ("start", "end"):
            raw = safe_strip(match.group(group_name))
            if not raw:
                continue
            if raw.lower() in ("present", "current"):
                years.append(current_year)
            else:
                # Extract the 4-digit year
                year_match = re.search(r"\d{4}", raw)
                if year_match:
                    years.append(int(year_match.group(0)))

    if len(years) < 2:
        return None

    return max(years) - min(years)


def _is_section_header(line: str) -> bool:
    """
    Heuristic: a section header is a short line that is all-caps or matches
    a known resume section keyword.
    """
    stripped = line.strip()
    if not stripped:
        return False

    known_headers = {
        "experience", "work experience", "employment", "education",
        "projects", "certifications", "awards", "publications",
        "languages", "interests", "summary", "objective", "references",
    }

    if stripped.lower() in known_headers:
        return True

    # All-caps short line (e.g. "EXPERIENCE", "EDUCATION")
    if stripped.isupper() and len(stripped.split()) <= 4:
        return True

    return False
