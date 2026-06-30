"""
src/parsers/csv_parser.py
-------------------------
WHY THIS FILE EXISTS
-------------------------
The recruiter fills in a CSV spreadsheet with candidate information. This
module reads that CSV, maps its columns to our internal CandidateRecord
shape, and passes it downstream. It never normalises data — that is the
Normalizer's job. It only extracts and maps.

PIPELINE CONNECTION
-------------------
  main.py  →  csv_parser.parse(path)  →  CandidateRecord (source="CSV")
  The CandidateRecord goes straight to the Merger.

COLUMN MAPPING
--------------
The CSV is expected to have these columns (case-insensitive):
  full_name, email, phone, city, region, country, linkedin,
  years_experience, skills, timestamp

Missing columns are tolerated — that field becomes None/[].
Skills are expected as a comma-separated value within one cell:
  "Python, JavaScript, SQL"
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from src.models.schema import CandidateRecord, LocationData, LinksData
from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
# WHY: Raising a generic Exception gives callers no structured way to handle
# parse failures. A named ParseError lets the CLI catch specifically this
# error and log a clear message without catching unrelated errors by mistake.
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when a source file cannot be parsed."""


# ---------------------------------------------------------------------------
# Column name aliases
# ---------------------------------------------------------------------------
# WHY: Recruiters name columns differently ("Email", "email address",
# "e-mail"). Maintaining an alias list here means the parser handles real
# messy CSVs without requiring the recruiter to rename their spreadsheet.
#
# HOW IT WORKS: We lowercase all header names and look up each one in this
# map to find what canonical field it corresponds to.
# ---------------------------------------------------------------------------
_COLUMN_ALIASES: dict[str, str] = {
    # full_name
    "full_name": "full_name",
    "name": "full_name",
    "candidate_name": "full_name",
    "fullname": "full_name",
    # email
    "email": "email",
    "email_address": "email",
    "e-mail": "email",
    "emails": "email",
    # phone
    "phone": "phone",
    "phone_number": "phone",
    "mobile": "phone",
    "telephone": "phone",
    "phones": "phone",
    # location
    "city": "city",
    "region": "region",
    "state": "region",
    "province": "region",
    "country": "country",
    # links
    "linkedin": "linkedin",
    "linkedin_url": "linkedin",
    # experience
    "years_experience": "years_experience",
    "years experience": "years_experience",
    "experience_years": "years_experience",
    # skills
    "skills": "skills",
    "skill_set": "skills",
    "technologies": "skills",
    # timestamp
    "timestamp": "timestamp",
    "date": "timestamp",
    "updated_at": "timestamp",
}


def _map_headers(raw_headers: list[str]) -> dict[str, str]:
    """
    Build a mapping of {canonical_field: actual_csv_column} from CSV headers.

    Args:
        raw_headers: List of column names exactly as they appear in the CSV.

    Returns:
        Dict mapping each canonical field name to the matching CSV column
        header (original casing preserved for lookup), or an empty dict
        entry if no matching column was found.

    CONCEPT — dictionary comprehension:
        {key: value for item in iterable} builds a dict in one expression.
        This is idiomatic Python and more readable than a for-loop for
        simple transformations.
    """
    # Build a lookup: lowercase_header -> original_header
    lower_to_original = {h.strip().lower(): h.strip() for h in raw_headers}

    mapping: dict[str, str] = {}
    for lower_header, original_header in lower_to_original.items():
        canonical = _COLUMN_ALIASES.get(lower_header)
        if canonical and canonical not in mapping:
            mapping[canonical] = original_header

    return mapping


def _get_cell(row: dict[str, str], column: Optional[str]) -> Optional[str]:
    """
    Safely get a cell value from a CSV row dict.

    Returns None if the column is missing or the cell is empty/whitespace.
    """
    if not column:
        return None
    return safe_strip(row.get(column))


def parse(csv_path: str) -> CandidateRecord:
    """
    Parse a recruiter CSV file and return a CandidateRecord.

    This function reads only the FIRST data row. A more advanced version
    would handle multi-candidate CSVs — that is a natural extension point.

    Args:
        csv_path: Path to the recruiter CSV file.

    Returns:
        CandidateRecord with source="CSV" and all extractable fields populated.

    Raises:
        ParseError: If the file cannot be opened or read.
    """
    path = Path(csv_path)

    # Requirement 2.3: Raise a descriptive ParseError (not a raw OSError)
    if not path.exists():
        raise ParseError(f"CSV file not found: {csv_path}")

    logger.info("Parsing CSV file: %s", csv_path)

    # Try multiple encodings — Excel often saves as cp1252 or latin-1
    _ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

    file_handle = None
    used_encoding = None
    for enc in _ENCODINGS:
        try:
            file_handle = open(path, newline="", encoding=enc)
            # Read a small chunk to verify the encoding works
            file_handle.read(512)
            file_handle.seek(0)
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            if file_handle:
                file_handle.close()
                file_handle = None

    if file_handle is None:
        raise ParseError(f"Could not decode CSV file {csv_path} — tried encodings: {_ENCODINGS}")

    logger.debug("CSV opened with encoding: %s", used_encoding)

    try:
        with file_handle as f:
            # csv.DictReader reads each row as a dict keyed by column header.
            # utf-8-sig strips the BOM character Excel sometimes adds.
            reader = csv.DictReader(f)

            if reader.fieldnames is None:
                raise ParseError(f"CSV file appears to be empty: {csv_path}")

            header_map = _map_headers(list(reader.fieldnames))
            logger.debug("CSV column mapping: %s", header_map)

            # Read only the first candidate row
            # CONCEPT — next() with a default:
            #   next(iterator, default) returns the next item or `default`
            #   if the iterator is exhausted. This avoids a StopIteration
            #   exception on an empty CSV.
            row = next(iter(reader), None)

            if row is None:
                raise ParseError(f"CSV file has headers but no data rows: {csv_path}")

        # --- Extract fields using the header map ---

        full_name = _get_cell(row, header_map.get("full_name"))

        # Emails: one cell, potentially semicolon/comma-separated
        email_raw = _get_cell(row, header_map.get("email"))
        emails = _split_list_cell(email_raw)

        # Phones: same pattern
        phone_raw = _get_cell(row, header_map.get("phone"))
        phones = _split_list_cell(phone_raw)

        # Location
        location = LocationData(
            city=_get_cell(row, header_map.get("city")),
            region=_get_cell(row, header_map.get("region")),
            country=_get_cell(row, header_map.get("country")),
        )

        # Links
        links = LinksData(
            linkedin=_get_cell(row, header_map.get("linkedin")),
        )

        # Years experience — convert to int safely
        years_raw = _get_cell(row, header_map.get("years_experience"))
        years_experience = _parse_int(years_raw, field_name="years_experience")

        # Skills: comma-separated in one cell
        skills_raw = _get_cell(row, header_map.get("skills"))
        skills = _split_list_cell(skills_raw)

        timestamp = _get_cell(row, header_map.get("timestamp"))

        record = CandidateRecord(
            source="CSV",
            full_name=full_name,
            emails=emails,
            phones=phones,
            location=location,
            links=links,
            years_experience=years_experience,
            skills=skills,
            timestamp=timestamp,
        )

        logger.info(
            "CSV parsed successfully — name=%r, emails=%d, phones=%d, skills=%d",
            full_name,
            len(emails),
            len(phones),
            len(skills),
        )

        return record

    except ParseError:
        # Re-raise our own errors without wrapping them
        raise
    except Exception as exc:
        # Wrap any unexpected error in ParseError so the CLI handles it cleanly
        raise ParseError(f"Failed to parse CSV file {csv_path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _split_list_cell(raw: Optional[str]) -> list[str]:
    """
    Split a comma-or-semicolon-separated cell value into a list of strings.

    Example:
        "Python, JavaScript; SQL" -> ["Python", "JavaScript", "SQL"]
    """
    if not raw:
        return []
    # Replace semicolons with commas, then split
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _parse_int(raw: Optional[str], field_name: str = "") -> Optional[int]:
    """
    Safely parse a string to int, logging a warning on failure.

    Returns None rather than crashing if the value is not numeric.
    """
    if not raw:
        return None
    try:
        return int(float(raw))   # float() first handles "5.0" correctly
    except (ValueError, TypeError):
        logger.warning("Could not convert %r to int for field %r", raw, field_name)
        return None
