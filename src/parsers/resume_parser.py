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
# PyMuPDF — embedded hyperlink extractor
# ---------------------------------------------------------------------------
# WHY PyMuPDF (fitz)?
#   pdfplumber extracts visible text. But many resumes have hyperlinks like
#   "LinkedIn" or "GitHub" where the display text hides the actual URL.
#   These URLs live in the PDF's annotation layer — invisible to text
#   extraction but readable by fitz.
#
#   Strategy:
#     1. Use fitz to iterate every page's link annotations.
#     2. For each annotation that has a URI, collect it.
#     3. Classify the URI into linkedin / github / portfolio / other.
#     4. Merge with regex-extracted URLs (fitz wins when both found).
# ---------------------------------------------------------------------------

def _extract_embedded_links(pdf_path: str) -> LinksData:
    """
    Use PyMuPDF (fitz) to extract embedded hyperlink annotations from a PDF.

    This catches URLs that are hidden behind display text like "LinkedIn" or
    "GitHub Portfolio" — common in professionally formatted resumes.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        LinksData with classified URLs.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("PyMuPDF not installed — skipping embedded link extraction.")
        return LinksData()

    linkedin:  Optional[str] = None
    github:    Optional[str] = None
    portfolio: Optional[str] = None
    other:     list[str]     = []

    _SEEN: set[str] = set()

    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            # page.get_links() returns a list of dicts with 'uri' key for web links
            for link in page.get_links():
                uri = link.get("uri", "").strip()
                if not uri or uri in _SEEN:
                    continue
                _SEEN.add(uri)

                uri_lower = uri.lower()

                if "linkedin.com" in uri_lower:
                    if not linkedin:
                        linkedin = uri
                elif "github.com" in uri_lower:
                    if not github:
                        github = uri
                elif any(d in uri_lower for d in [
                    "leetcode.com", "hackerrank.com", "codeforces.com",
                    "kaggle.com", "stackoverflow.com", "codepen.io",
                    "behance.net", "dribbble.com", "medium.com",
                    "codolio.com", "devpost.com",
                ]):
                    other.append(uri)
                elif uri_lower.startswith(("http://", "https://")):
                    # Treat as portfolio if no portfolio yet, else other
                    if not portfolio and _looks_like_portfolio(uri):
                        portfolio = uri
                    else:
                        other.append(uri)

        doc.close()
        logger.info(
            "Embedded links extracted — linkedin=%s, github=%s, portfolio=%s, other=%d",
            bool(linkedin), bool(github), bool(portfolio), len(other),
        )

    except Exception as exc:
        logger.warning("PyMuPDF link extraction failed: %s", exc)

    return LinksData(
        linkedin=linkedin,
        github=github,
        portfolio=portfolio,
        other=list(dict.fromkeys(other)),  # deduplicate, preserve order
    )


def _looks_like_portfolio(uri: str) -> bool:
    """Heuristic: a portfolio URL is personal (not a known platform)."""
    _NOT_PORTFOLIO = {
        "google.com", "youtube.com", "twitter.com", "x.com",
        "facebook.com", "instagram.com", "reddit.com",
        "microsoft.com", "apple.com", "amazon.com",
    }
    from urllib.parse import urlparse
    try:
        host = urlparse(uri).netloc.lower().replace("www.", "")
        return host not in _NOT_PORTFOLIO
    except Exception:
        return False


def _merge_links(regex_links: LinksData, fitz_links: LinksData) -> LinksData:
    """
    Merge regex-extracted links with PyMuPDF-extracted links.
    fitz wins when both have a value (annotation URLs are more reliable).
    """
    other = list(dict.fromkeys(
        (fitz_links.other or []) + (regex_links.other or [])
    ))
    return LinksData(
        linkedin  = fitz_links.linkedin  or regex_links.linkedin,
        github    = fitz_links.github    or regex_links.github,
        portfolio = fitz_links.portfolio or regex_links.portfolio,
        other     = other,
    )


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

# Skills section header — matches ALL skill-related section headers:
# "Skills", "Technical Skills", "Soft Skills", "Core Skills",
# "Tools & Technologies", "Extracurricular", "Activities", etc.
_RE_SKILLS_HEADER = re.compile(
    r"^\s*(?:"
    r"(?:technical\s+|soft\s+|core\s+|key\s+|professional\s+|transferable\s+)?"
    r"skills?|"
    r"tools?\s*(?:&|and)?\s*(?:technologies|tech|frameworks?)?|"
    r"technologies|tech\s*stack|"
    r"competenc(?:y|ies)|capabilities|"
    r"extra[\s\-]?curricular|activities|"
    r"hobbies\s*(?:&|and)?\s*interests?|"
    r"interests?|strengths?"
    r")\s*[:\-]?\s*$",
    re.IGNORECASE,
)

# Sub-section header WITHIN a skills block.
# Handles both "Soft Skills:" and "Programming Languages : C, C++, Java"
# The key insight: these lines have a LABEL part followed by : then VALUES.
# We strip the label and keep the values.
_RE_SKILLS_SUBSECTION = re.compile(
    r"^\s*(?:"
    r"(?:technical|soft|core|key|professional|hard|other)\s+skills?"
    r"|programming\s+languages?"
    r"|tools?\s*(?:&|and)?\s*(?:technologies|frameworks?)?"
    r"|web\s+technologies|backend\s*(?:&|and)?\s*frameworks?"
    r"|core\s+(?:cs\s+)?concepts?"
    r"|databases?|version\s+control|cloud"
    r"|languages?|frameworks?|platforms?"
    r"|extra[\s\-]?curricular|activities|achievements?"
    r")\s*[:\s]\s*",   # colon OR space-colon-space separator
    re.IGNORECASE,
)

# Generic "Label : values" pattern — catches ANY subsection line within skills block
# that follows the format "SomeLabel : comma, separated, values"
_RE_LABEL_VALUES = re.compile(
    r"^([A-Za-z][A-Za-z\s&\(\)]+?)\s*:\s*(.+)$"
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

    # --- Extract embedded hyperlinks via PyMuPDF (fitz) ---
    # This runs regardless of whether AI or regex is used for text fields,
    # because link annotations are separate from text content.
    fitz_links = _extract_embedded_links(pdf_path)
    logger.debug("PyMuPDF links: %s", fitz_links)

    # --- Try AI extraction first, fall back to regex ---
    from src.parsers import ai_resume_parser

    if ai_resume_parser.is_available() and full_text:
        ai_record = ai_resume_parser.extract(full_text)
        if ai_record:
            logger.info("Using AI-extracted resume record.")
            # Merge AI-extracted links with fitz-extracted links
            ai_record.links = _merge_links(ai_record.links, fitz_links)
            return ai_record
        logger.warning("AI extraction failed — falling back to regex parser.")

    # --- Regex fallback ---
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

    # Merge regex links with fitz links
    regex_links = LinksData(linkedin=linkedin, github=github, portfolio=portfolio)
    merged_links = _merge_links(regex_links, fitz_links)

    record = CandidateRecord(
        source="Resume",
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=merged_links,
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
    Extract all skills from resume text — technical, soft, and extracurricular.

    Handles multiple formats:
      - Single "Skills" section with comma/pipe/bullet delimited items
      - Sub-sections: "Technical Skills:", "Soft Skills:", "Tools:", etc.
      - Standalone "Extracurricular Activities" section
      - Inline skill lists on one or multiple lines

    Stops collecting when it hits a non-skills major section header.
    """
    lines = text.split("\n")
    skills_lines: list[str] = []
    in_skills_block = False

    for line in lines:
        stripped = line.strip()

        # ── Start a new skills block ──────────────────────────
        if _RE_SKILLS_HEADER.match(stripped):
            in_skills_block = True
            # Skills may start on the same line after the header label
            after_header = re.sub(
                r"^\s*(?:technical\s+|soft\s+|core\s+|key\s+|professional\s+|"
                r"transferable\s+|hard\s+|other\s+)?skills?\s*[:&/]?\s*|"
                r"^\s*tools?\s*(?:&|and)?\s*(?:technologies|tech|frameworks?)?\s*[:]\s*|"
                r"^\s*extra[\s\-]?curricular\s*(?:activities)?\s*[:]\s*|"
                r"^\s*activities\s*[:]\s*|"
                r"^\s*interests?\s*[:]\s*|"
                r"^\s*strengths?\s*[:]\s*",
                "", stripped, flags=re.IGNORECASE
            ).strip()
            if after_header:
                skills_lines.append(after_header)
            continue

        if in_skills_block:
            # ── Sub-section header within skills block ────────
            # Pattern 1: known subsection keyword — strip label, keep values
            sub_match = _RE_SKILLS_SUBSECTION.match(stripped)
            if sub_match:
                after_sub = stripped[sub_match.end():].strip()
                if after_sub:
                    skills_lines.append(after_sub)
                continue

            # Pattern 2: generic "Label : values" line e.g. "Programming Languages : C, C++, Java"
            # Only treat as label:values if the label part is short (< 40 chars)
            lv_match = _RE_LABEL_VALUES.match(stripped)
            if lv_match and len(lv_match.group(1)) < 40:
                # Keep only the values part
                skills_lines.append(lv_match.group(2).strip())
                continue

            # ── Stop on a major non-skills section ───────────
            if _is_major_section_header(stripped):
                break

            # ── Collect this line ─────────────────────────────
            if stripped:
                skills_lines.append(stripped)

    # Split collected lines on common delimiters (comma, pipe, bullet)
    # Keep space-separated lines intact for now — handle per-line
    result: list[str] = []
    seen:   set[str]  = set()

    for line in skills_lines:
        line = line.strip()
        if not line:
            continue

        # If the line contains commas/pipes/bullets → comma-split (skills are explicit)
        if re.search(r"[,|•·]", line):
            items = re.split(r"[,|•·]+", line)
        else:
            # Remove leading bullet/dash before space-split
            line_clean = re.sub(r"^[\-–•·]\s*", "", line)
            items = _maybe_split_space_skills(line_clean)

        for item in items:
            skill = item.strip().strip("•·–-").strip()
            if (
                skill
                and 2 <= len(skill) <= 50
                and not _RE_SKILLS_SUBSECTION.match(skill + ":")
                and not re.match(r"^\d+[\.\)]\s*", skill)
                and len(skill.split()) <= 5   # single skill, not a sentence
            ):
                key = skill.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(skill)

    return result

    return result


def _maybe_split_space_skills(item: str) -> list[str]:
    """
    Detect and split space-separated skill lists like:
      "C++ Html Git SpringBoot SQL"  →  ["C++", "Html", "Git", "SpringBoot", "SQL"]

    Only splits if:
    - Item has 2+ space-separated tokens
    - Each token is short (≤ 20 chars)
    - No token looks like a sentence word (no common English stop words)
    - Not a label:value line (already handled)

    Returns the original item in a list if it shouldn't be split.
    """
    tokens = item.split()
    if len(tokens) < 2:
        return [item]

    # If all tokens are short skill-like words, split them
    _SENTENCE_WORDS = {
        "and", "or", "the", "a", "an", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "are", "was", "were",
        "be", "been", "have", "has", "had", "do", "did", "will", "would",
        "can", "could", "should", "may", "might", "shall", "not", "no",
        "its", "it", "this", "that", "these", "those", "my", "your",
    }

    all_short = all(len(t) <= 25 for t in tokens)
    no_sentence_words = not any(t.lower() in _SENTENCE_WORDS for t in tokens)
    no_long_token = not any(len(t) > 20 for t in tokens)

    if all_short and no_sentence_words and no_long_token and len(tokens) <= 8:
        return tokens

    return [item]


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
    return _is_major_section_header(line)


def _is_major_section_header(line: str) -> bool:
    """
    Returns True if the line is a major resume section header that should
    STOP skill collection. Skills sub-sections are NOT major headers.
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Major sections that terminate skill collection
    _MAJOR_SECTIONS = {
        "experience", "work experience", "professional experience",
        "employment", "employment history",
        "education", "academic background", "qualifications",
        "projects", "personal projects", "academic projects",
        "certifications", "certificates", "achievements", "awards",
        "publications", "research",
        "summary", "objective", "profile", "about",
        "references", "declaration",
        "internship", "internships",
        "competitive programming", "competitive",
        "certifications & courses",
    }

    lower = stripped.lower()

    # Exact match against known major sections
    if lower in _MAJOR_SECTIONS:
        return True

    # All-caps short line (e.g. "EXPERIENCE", "EDUCATION", "PROJECTS")
    # BUT skip if it matches the skills header pattern
    if stripped.isupper() and 2 <= len(stripped.split()) <= 4:
        # Don't stop on skills-related headers
        if _RE_SKILLS_HEADER.match(stripped):
            return False
        return True

    return False
