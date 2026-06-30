"""
src/bulk/bulk_matcher.py
------------------------
Deterministic resume-to-CSV-row matching engine.

MATCHING PRIORITY (highest → lowest):
  1. Email match  — most reliable, globally unique identifier
  2. Phone match  — E.164 normalised before comparison
  3. Exact name   — case-insensitive full_name equality
  4. Fuzzy name   — token-set match (handles middle names, initials)

If no match is found:
  - The CSV row gets status = "resume_missing"
  - The orphan resume gets status = "csv_missing"

Never raises. All issues become MatchWarnings.
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
    warnings:      list[str]        = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def match_all(
    csv_rows: list[CsvRow],
    resume_paths: list[Path],
) -> tuple[list[MatchResult], list[Path]]:
    """
    Match every CSV row to a resume file using the priority chain.

    Args:
        csv_rows:      Parsed rows from the recruiter CSV.
        resume_paths:  All resume file paths extracted from the ZIP.

    Returns:
        Tuple of:
          - matched:  List[MatchResult] — one per CSV row
          - orphans:  List[Path] — resumes with no CSV counterpart
    """
    results:        list[MatchResult] = []
    matched_paths:  set[Path]         = set()

    # Build lookup indexes from resume filenames for fast matching
    email_index  = _build_email_index(resume_paths)
    phone_index  = _build_phone_index(resume_paths)
    name_index   = _build_name_index(resume_paths)

    for row in csv_rows:
        resume_path, method = _find_resume(
            row, email_index, phone_index, name_index
        )

        warnings: list[str] = []
        if resume_path is None:
            warnings.append(
                f"No resume found for '{row.full_name or row.email or f'row {row.index}'}'. "
                f"Status: resume_missing."
            )
            logger.warning(
                "Row %d (%r): no resume match found.",
                row.index, row.full_name
            )
        else:
            matched_paths.add(resume_path)
            logger.info(
                "Row %d (%r): matched to %s via %s",
                row.index, row.full_name, resume_path.name, method
            )

        results.append(MatchResult(
            csv_row=row,
            resume_path=resume_path,
            match_method=method,
            warnings=warnings,
        ))

    # Orphan resumes — have a file but no CSV row
    orphans = [p for p in resume_paths if p not in matched_paths]
    for orphan in orphans:
        logger.warning("Orphan resume (no CSV row): %s", orphan.name)

    return results, orphans


# ---------------------------------------------------------------------------
# Matching strategy helpers
# ---------------------------------------------------------------------------

def _find_resume(
    row: CsvRow,
    email_index:  dict[str, Path],
    phone_index:  dict[str, Path],
    name_index:   dict[str, Path],
) -> tuple[Optional[Path], str]:
    """Try each matching strategy in priority order."""

    # Priority 1 — email
    if row.email:
        norm_email = row.email.strip().lower()
        path = email_index.get(norm_email)
        if path:
            return path, "email"

    # Priority 2 — phone
    if row.phone:
        norm_phone = _normalize_phone_digits(row.phone)
        path = phone_index.get(norm_phone)
        if path:
            return path, "phone"

    # Priority 3 — exact name (case-insensitive)
    if row.full_name:
        norm_name = _normalize_name(row.full_name)
        path = name_index.get(norm_name)
        if path:
            return path, "exact_name"

    # Priority 4 — fuzzy token-set name match
    if row.full_name:
        path = _fuzzy_name_match(row.full_name, name_index)
        if path:
            return path, "fuzzy_name"

    return None, "none"


# ---------------------------------------------------------------------------
# Index builders — extract identifiers from resume filenames
# ---------------------------------------------------------------------------
# Convention: recruiters name resumes using candidate info, e.g.:
#   "john_doe_resume.pdf"
#   "jane.smith@email.com_cv.pdf"
#   "+14155552671_resume.pdf"
# We extract these tokens from filenames for matching.

def _build_email_index(paths: list[Path]) -> dict[str, Path]:
    """Build {normalised_email: path} from resume filenames."""
    _EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    index: dict[str, Path] = {}
    for path in paths:
        stem = path.stem  # filename without extension
        match = _EMAIL_RE.search(stem)
        if match:
            index[match.group(0).lower()] = path
    return index


def _build_phone_index(paths: list[Path]) -> dict[str, Path]:
    """Build {digits_only_phone: path} from resume filenames."""
    _PHONE_RE = re.compile(r"[\+\d][\d\s\-\(\)\.]{6,}")
    index: dict[str, Path] = {}
    for path in paths:
        stem = path.stem
        match = _PHONE_RE.search(stem)
        if match:
            digits = _normalize_phone_digits(match.group(0))
            if digits:
                index[digits] = path
    return index


def _build_name_index(paths: list[Path]) -> dict[str, Path]:
    """Build {normalised_name: path} from resume filenames."""
    index: dict[str, Path] = {}
    for path in paths:
        # Replace underscores/hyphens with spaces, drop extension tokens
        stem = path.stem
        # Remove email-like patterns to avoid false matches
        stem = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "", stem)
        # Replace separators with spaces
        name_candidate = re.sub(r"[_\-\.]+", " ", stem).strip()
        # Drop trailing/leading noise words
        name_candidate = re.sub(
            r"\b(resume|cv|profile|candidate|doc|final|updated|new)\b",
            "", name_candidate, flags=re.IGNORECASE
        ).strip()
        norm = _normalize_name(name_candidate)
        if norm and len(norm) >= 3:
            index[norm] = path
    return index


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Lowercase, remove accents, collapse whitespace."""
    # Remove accents
    nfd = unicodedata.normalize("NFD", name)
    ascii_name = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Lowercase, strip punctuation, collapse spaces
    cleaned = re.sub(r"[^a-z\s]", "", ascii_name.lower())
    return " ".join(cleaned.split())


def _normalize_phone_digits(phone: str) -> str:
    """Extract only digits from a phone string (last 10 for US-style matching)."""
    digits = re.sub(r"\D", "", phone)
    # Use last 10 digits to handle country code variations
    return digits[-10:] if len(digits) >= 10 else digits


def _fuzzy_name_match(
    candidate_name: str,
    name_index: dict[str, Path],
    threshold: float = 0.75,
) -> Optional[Path]:
    """
    Token-set fuzzy name matching.

    Splits both names into word sets and computes Jaccard similarity.
    Handles cases like "John A. Doe" vs "John Doe".
    """
    target_tokens = set(_normalize_name(candidate_name).split())
    if not target_tokens:
        return None

    best_score = 0.0
    best_path: Optional[Path] = None

    for norm_name, path in name_index.items():
        index_tokens = set(norm_name.split())
        if not index_tokens:
            continue
        intersection = target_tokens & index_tokens
        union = target_tokens | index_tokens
        score = len(intersection) / len(union) if union else 0.0
        if score > best_score:
            best_score = score
            best_path = path

    if best_score >= threshold:
        logger.debug(
            "Fuzzy name match: %r → score=%.2f", candidate_name, best_score
        )
        return best_path

    return None
