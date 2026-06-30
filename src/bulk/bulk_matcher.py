"""
src/bulk/bulk_matcher.py
------------------------
Deterministic resume-to-CSV-row matching engine.

MATCHING PRIORITY (highest → lowest):
  1. Email     — most reliable, globally unique
  2. Phone     — normalised to E.164 digits before comparison
  3. Exact Name — normalised (no accents, no case, no initials, no punctuation)
  4. Fuzzy Name — RapidFuzz token_set_ratio >= 90

MATCHING SOURCES for each resume:
  - Filename tokens (email / phone / name embedded in filename)
  - PDF text content (extracted by pdfplumber, searched for email & phone)

Name normalisation strips:
  - Accents / diacritics
  - Uppercase / lowercase differences
  - Trailing single-character initials (e.g. "HAZEENA S" → "hazeena")
  - Dots, commas, extra whitespace

If no match found:
  csv_row  → status = "resume_missing"
  orphan   → status = "csv_missing"

Never raises — all issues become warnings in MatchResult.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# RapidFuzz — optional, falls back to Jaccard if not installed
# ---------------------------------------------------------------------------
try:
    from rapidfuzz import fuzz as _fuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not installed — using Jaccard similarity for fuzzy matching.")

# Fuzzy match threshold (0–100 scale for RapidFuzz, 0–1 for Jaccard fallback)
_FUZZY_THRESHOLD_RF  = 90    # RapidFuzz token_set_ratio
_FUZZY_THRESHOLD_JAC = 0.75  # Jaccard fallback


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CsvRow:
    """One row from the recruiter CSV (raw strings, un-normalised)."""
    index:     int
    full_name: Optional[str]
    email:     Optional[str]
    phone:     Optional[str]
    raw:       dict            # original row dict for csv_parser reuse


@dataclass
class MatchResult:
    """Outcome of matching one CSV row to a resume file."""
    csv_row:       CsvRow
    resume_path:   Optional[Path]   # None → "resume_missing"
    match_method:  str              # "email"|"phone"|"exact_name"|"fuzzy_name"|"none"
    match_score:   float            = 1.0
    warnings:      list[str]        = field(default_factory=list)


# ---------------------------------------------------------------------------
# Resume index — extracted identifiers per resume file
# ---------------------------------------------------------------------------

@dataclass
class ResumeIndex:
    """All identifiable tokens extracted from one resume file."""
    path:        Path
    emails:      set[str]   = field(default_factory=set)   # lowercase
    phones:      set[str]   = field(default_factory=set)   # last-10-digits
    norm_name:   str        = ""                           # normalised name from filename


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_all(
    csv_rows:     list[CsvRow],
    resume_paths: list[Path],
) -> tuple[list[MatchResult], list[Path]]:
    """
    Match every CSV row to a resume file using the priority chain.

    Strategy:
      For each resume, extract emails and phones from BOTH the filename
      AND the PDF text content. This handles resumes not named after the
      candidate (e.g. "resume.pdf") by reading the actual content.

    Args:
        csv_rows:      All rows from the recruiter CSV.
        resume_paths:  All resume paths extracted from the ZIP.

    Returns:
        (matched_results, orphan_paths)
    """
    # Build per-resume index (filename + PDF content scan)
    resume_indexes = [_build_resume_index(p) for p in resume_paths]

    results:       list[MatchResult] = []
    matched_paths: set[Path]         = set()

    for row in csv_rows:
        best = _find_best_match(row, resume_indexes, matched_paths)

        if best is None:
            logger.warning(
                "Row %d (%r): no resume match found → resume_missing",
                row.index, row.full_name
            )
            results.append(MatchResult(
                csv_row=row,
                resume_path=None,
                match_method="none",
                warnings=[
                    f"No resume found for "
                    f"'{row.full_name or row.email or f'row {row.index}'}'. "
                    f"Status: resume_missing."
                ],
            ))
        else:
            matched_paths.add(best.resume_path)
            logger.info(
                "Row %d (%r): matched '%s' via %s (score=%.1f)",
                row.index, row.full_name,
                best.resume_path.name, best.match_method, best.match_score,
            )
            results.append(best)

    # Orphans: resumes that didn't match any CSV row
    orphans = [ri.path for ri in resume_indexes if ri.path not in matched_paths]
    for orphan in orphans:
        logger.warning("Orphan resume (no CSV row): %s", orphan.name)

    return results, orphans


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def _find_best_match(
    row:           CsvRow,
    resume_indexes: list[ResumeIndex],
    already_matched: set[Path],
) -> Optional[MatchResult]:
    """
    Try all strategies in priority order.
    Returns the best MatchResult or None.
    """
    candidates: list[MatchResult] = []

    # Normalise row identifiers once
    row_email       = row.email.strip().lower() if row.email else None
    row_phone_digits = _phone_to_digits(row.phone) if row.phone else None
    row_norm_name   = normalize_name(row.full_name) if row.full_name else ""

    for ri in resume_indexes:
        if ri.path in already_matched:
            continue

        # ── Priority 1: Email ──────────────────────────────────
        if row_email and row_email in ri.emails:
            candidates.append(MatchResult(
                csv_row=row, resume_path=ri.path,
                match_method="email", match_score=100.0,
            ))
            continue   # email is definitive — no need to check lower priorities

        # ── Priority 2: Phone ──────────────────────────────────
        if row_phone_digits:
            for rp in ri.phones:
                # Compare last 10 digits to handle country-code differences
                if _digits_match(row_phone_digits, rp):
                    candidates.append(MatchResult(
                        csv_row=row, resume_path=ri.path,
                        match_method="phone", match_score=95.0,
                    ))
                    break

        # ── Priority 3: Exact name ─────────────────────────────
        if row_norm_name and ri.norm_name and row_norm_name == ri.norm_name:
            candidates.append(MatchResult(
                csv_row=row, resume_path=ri.path,
                match_method="exact_name", match_score=85.0,
            ))
            continue

        # ── Priority 4: Fuzzy name ─────────────────────────────
        if row_norm_name and ri.norm_name:
            score = _fuzzy_score(row_norm_name, ri.norm_name)
            if score >= _FUZZY_THRESHOLD_RF if _RAPIDFUZZ_AVAILABLE else score >= _FUZZY_THRESHOLD_JAC:
                norm_score = score if _RAPIDFUZZ_AVAILABLE else score * 100
                candidates.append(MatchResult(
                    csv_row=row, resume_path=ri.path,
                    match_method="fuzzy_name", match_score=float(norm_score),
                ))

    if not candidates:
        return None

    # Pick the highest-confidence match
    # Priority order: email > phone > exact_name > fuzzy_name, then by score
    _PRIORITY = {"email": 4, "phone": 3, "exact_name": 2, "fuzzy_name": 1, "none": 0}
    best = max(
        candidates,
        key=lambda m: (_PRIORITY.get(m.match_method, 0), m.match_score)
    )
    return best


# ---------------------------------------------------------------------------
# Resume index builder
# ---------------------------------------------------------------------------

# Compiled patterns used during content scan
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)?\d{3}[\s\-.]?\d{4}"
)


def _build_resume_index(path: Path) -> ResumeIndex:
    """
    Extract all matchable identifiers from one resume file.

    Scans:
      1. Filename (emails, phones, name candidate)
      2. First 2 pages of PDF text (emails, phones)
         — only 2 pages keeps it fast; contact info is always near the top
    """
    ri = ResumeIndex(path=path)

    stem = path.stem

    # ── From filename ──────────────────────────────────────────
    # Emails in filename
    for m in _EMAIL_RE.finditer(stem):
        ri.emails.add(m.group(0).lower())

    # Phones in filename
    for m in _PHONE_RE.finditer(stem):
        d = _phone_to_digits(m.group(0))
        if d and len(d) >= 7:
            ri.phones.add(d)

    # Name candidate from filename (remove emails, noise words, separators)
    name_stem = _EMAIL_RE.sub("", stem)
    name_stem = re.sub(r"[_\-\.]+", " ", name_stem)
    name_stem = re.sub(
        r"\b(resume|cv|profile|candidate|doc|final|updated|new|application)\b",
        " ", name_stem, flags=re.IGNORECASE
    )
    ri.norm_name = normalize_name(name_stem.strip())

    # ── From PDF text (first 2 pages) ─────────────────────────
    if path.suffix.lower() == ".pdf":
        text = _extract_pdf_head(path, pages=2)
        if text:
            # Emails in text
            for m in _EMAIL_RE.finditer(text):
                ri.emails.add(m.group(0).lower())

            # Phones in text — use the improved extractor
            for phone_str in _extract_phones_from_text(text):
                d = _phone_to_digits(phone_str)
                if d and len(d) >= 7:
                    ri.phones.add(d)

            # If no name from filename, try first line of PDF
            if not ri.norm_name:
                first_line = _extract_name_from_text(text)
                if first_line:
                    ri.norm_name = normalize_name(first_line)

    logger.debug(
        "Index built: %s → emails=%s phones=%s name=%r",
        path.name, ri.emails, ri.phones, ri.norm_name,
    )
    return ri


def _extract_pdf_head(path: Path, pages: int = 2) -> str:
    """Extract text from the first N pages of a PDF. Returns "" on failure."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            parts = []
            for page in pdf.pages[:pages]:
                t = page.extract_text()
                if t:
                    parts.append(t)
            return "\n".join(parts)
    except Exception as exc:
        logger.debug("PDF text extraction failed for %s: %s", path.name, exc)
        return ""


def _extract_phones_from_text(text: str) -> list[str]:
    """
    Extract all phone-like strings from text using a comprehensive regex.
    Supports: 9876543210, +91 9876543210, +91-9876543210, 91 9876543210,
              (091)9876543210, +91(987)654-3210, etc.
    """
    # Comprehensive phone pattern covering Indian + international formats
    pattern = re.compile(
        r"(?<!\d)"                        # not preceded by a digit
        r"(\+?\d{1,3}[\s\-.]?)?"         # optional country code
        r"(\(?\d{3,5}\)?[\s\-.]?)"       # area code
        r"(\d{3,4}[\s\-.]?)"             # first part
        r"(\d{4})"                        # last 4 digits
        r"(?!\d)"                         # not followed by a digit
    )
    results = []
    for m in pattern.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15:
            results.append(raw)
    return results


def _extract_name_from_text(text: str) -> Optional[str]:
    """
    Heuristic: first non-empty line that looks like a name (2-5 alpha words).
    """
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        # Skip lines with digits, @, /, http (likely contact info)
        if re.search(r"[\d@/:]", line):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(re.match(r"[A-Za-z\'\-]+$", w) for w in words):
            return line
    return None


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalize_name(name: Optional[str]) -> str:
    """
    Produce a canonical name string for comparison.

    Steps:
      1. Unicode NFD → strip diacritics
      2. Lowercase
      3. Remove dots, commas, parentheses
      4. Collapse whitespace
      5. Remove trailing single-character tokens (initials like "S", "R")
         — handles "HAZEENA S" → "hazeena", "VENSILIN R" → "vensilin"
      6. Strip leftover whitespace

    Examples:
      "AYISHATHUL HAZEENA S"  → "ayishathul hazeena"
      "DAVID VENSILIN R"      → "david vensilin"
      "John A. Doe"           → "john doe"
      "O'Brien, Michael"      → "obrien michael"
    """
    if not name:
        return ""

    # 1. NFD + strip diacritics
    nfd = unicodedata.normalize("NFD", name)
    ascii_str = "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    # 2. Lowercase
    s = ascii_str.lower()

    # 3. Remove non-alphabetic except spaces (dots, commas, apostrophes, etc.)
    #    But first collapse apostrophes into nothing (O'Brien → OBrien)
    s = re.sub(r"'", "", s)
    s = re.sub(r"[^a-z\s]", " ", s)

    # 4. Collapse whitespace
    tokens = s.split()

    # 5. Remove single-character tokens (initials)
    tokens = [t for t in tokens if len(t) > 1]

    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Phone helpers
# ---------------------------------------------------------------------------

def _phone_to_digits(phone: Optional[str]) -> str:
    """Extract all digits from a phone string."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def _digits_match(a: str, b: str) -> bool:
    """
    Compare two digit strings by their last 10 digits.
    Handles country-code differences: "+919876543210" vs "9876543210".
    """
    a10 = a[-10:] if len(a) >= 10 else a
    b10 = b[-10:] if len(b) >= 10 else b
    return a10 == b10 and len(a10) >= 7


# ---------------------------------------------------------------------------
# Fuzzy scoring
# ---------------------------------------------------------------------------

def _fuzzy_score(a: str, b: str) -> float:
    """
    Return a similarity score between two normalised name strings.

    Uses RapidFuzz token_set_ratio (0–100) if available,
    otherwise Jaccard token similarity (0–1, converted to 0–100).

    token_set_ratio handles:
      - Different word order
      - One name being a subset of the other (middle names)
      - Minor typos
    """
    if not a or not b:
        return 0.0

    if _RAPIDFUZZ_AVAILABLE:
        return _fuzz.token_set_ratio(a, b)

    # Jaccard fallback
    sa = set(a.split())
    sb = set(b.split())
    union = sa | sb
    if not union:
        return 0.0
    score = len(sa & sb) / len(union)
    return score * 100  # normalise to 0–100 scale for consistent comparison
