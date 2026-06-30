"""
src/normalizers/dates.py
------------------------
WHY THIS FILE EXISTS
------------------------
Dates appear in every possible format: "Jan 2022", "2022-01", "January 2022",
"01/2022", "2022". ISO 8601 (YYYY-MM-DD) is the universal machine-readable
standard. This module converts anything parseable to ISO 8601 and discards
the rest gracefully.

PIPELINE CONNECTION
-------------------
  Called by the Resume parser when extracting experience dates.
  Input:  raw date string
  Output: ISO 8601 string "YYYY-MM-DD", or None if unparseable
"""

from __future__ import annotations

from typing import Optional

from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)

# Sentinel strings that mean "still employed here" — never try to parse these
_PRESENT_TOKENS = {"present", "current", "now", "today", "-"}


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """
    Parse a free-form date string and return it in ISO 8601 format.

    When only year+month are detectable, the day is set to 01.
    When the input represents "present"/"current", returns the string
    "Present" (not a date) so the merger can treat it correctly.

    Args:
        raw: Free-form date string (e.g. "Jan 2022", "2022-01-15", "2022").

    Returns:
        "YYYY-MM-DD" string, "Present", or None.

    Examples:
        normalize_date("Jan 2022")      -> "2022-01-01"
        normalize_date("2022-06-15")    -> "2022-06-15"
        normalize_date("Present")       -> "Present"
        normalize_date("garbage")       -> None  (warning logged)

    WHY python-dateutil:
        dateutil.parser.parse() handles an enormous variety of formats
        automatically. It is far more robust than strptime() with a fixed
        format string and covers almost every real-world date format.

    CONCEPT — dayfirst=False:
        Tells dateutil to interpret ambiguous dates like "01/02/2022" as
        Jan 2 (month first), not Feb 1. This is the US convention.
        Change to True for European-first formats.
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    # Check for "Present" / "Current" tokens before trying to parse
    if cleaned.lower() in _PRESENT_TOKENS:
        return "Present"

    try:
        parsed = dateutil_parser.parse(cleaned, dayfirst=False, default=None)
        return parsed.strftime("%Y-%m-%d")
    except (ParserError, ValueError, OverflowError):
        logger.warning("Could not parse date string: %r", raw)
        return None


def normalize_year_only(raw: Optional[str]) -> Optional[str]:
    """
    Handle year-only strings that dateutil might misinterpret.

    Args:
        raw: A 4-digit year string (e.g. "2019").

    Returns:
        "YYYY-01-01" or None.
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    if cleaned.isdigit() and len(cleaned) == 4:
        return f"{cleaned}-01-01"

    # Delegate to the general parser for everything else
    return normalize_date(cleaned)
