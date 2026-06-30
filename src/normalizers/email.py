"""
src/normalizers/email.py
------------------------
WHY THIS FILE EXISTS
------------------------
Email addresses from different sources may be "John@EXAMPLE.com" or
"john@example.COM". These are the same address but would appear as
duplicates if not normalised. This module enforces one canonical form.

PIPELINE CONNECTION
-------------------
  Called by the Merger after parsing, before deduplication.
  Input:  raw email string from CandidateRecord
  Output: lowercase email string, or None if invalid
"""

from __future__ import annotations

import re
from typing import Optional

from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# RFC 5321 email regex — simplified but production-reasonable
# ---------------------------------------------------------------------------
# WHY: We need to reject obviously bad values like "not-an-email" while
# accepting real addresses. A full RFC 5321 parser is overkill here;
# this pattern covers the vast majority of real-world addresses.
#
# CONCEPT — raw strings (r"..."):
#   The `r` prefix means Python treats backslashes literally instead of
#   as escape characters. Always use raw strings for regex patterns.
# ---------------------------------------------------------------------------
_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def normalize_email(raw: Optional[str]) -> Optional[str]:
    """
    Normalize a raw email string to lowercase and validate its format.

    Returns None (with a logged warning) if the email is missing or invalid.

    Args:
        raw: The raw email string from a parser.

    Returns:
        Lowercase, validated email string or None.

    Examples:
        normalize_email("John@Example.COM")  -> "john@example.com"
        normalize_email("not-an-email")      -> None  (warning logged)
        normalize_email(None)                -> None
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    lowered = cleaned.lower()

    if not _EMAIL_REGEX.match(lowered):
        logger.warning("Invalid email address skipped: %r", raw)
        return None

    return lowered


def normalize_emails(raw_list: list[str]) -> list[str]:
    """
    Normalize a list of raw email strings, dropping any that are invalid.

    Args:
        raw_list: List of raw email strings.

    Returns:
        Deduplicated list of valid, lowercased email strings.
    """
    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_list:
        normalised = normalize_email(raw)
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)

    return result
