"""
src/normalizers/phone.py
------------------------
WHY THIS FILE EXISTS
------------------------
Phone numbers appear in dozens of formats. E.164 is the universal standard.
This module converts any recognisable format into E.164 and discards the rest.

Supported formats (examples):
  9876543210          → +919876543210  (with country hint "IN")
  +91 9876543210      → +919876543210
  +91-9876543210      → +919876543210
  (+91)9876543210     → +919876543210
  91 9876543210       → +919876543210
  (415) 555-2671      → +14155552671  (with country hint "US")
  +44 20 7946 0958    → +442079460958

PIPELINE CONNECTION
-------------------
  Called by the Merger after parsing, before deduplication.
  country_hint must be ISO Alpha-2 (e.g. "IN", "US") — not a full name.
"""

from __future__ import annotations

import re
from typing import Optional

import phonenumbers
from phonenumbers import NumberParseException

from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pre-processing: clean common formatting noise before parsing
# ---------------------------------------------------------------------------

# Matches (+91), (091), etc. — brackets around country code are non-standard
_PAREN_CC_RE = re.compile(r"^\((\+?\d{1,4})\)\s*")


def _preprocess_phone(raw: str) -> str:
    """
    Clean formatting noise that confuses the phonenumbers parser.

    Examples:
      "(+91)9876543210"  → "+919876543210"
      "(091) 9876543210" → "0919876543210"
      "91 9876543210"    → "91 9876543210"  (unchanged — parser handles it)
    """
    cleaned = raw.strip()

    # Remove parentheses around country code: (+91)... → +91...
    m = _PAREN_CC_RE.match(cleaned)
    if m:
        cc = m.group(1)
        rest = cleaned[m.end():]
        cleaned = cc + rest

    # Normalise separators: dots and multiple spaces → single space
    cleaned = re.sub(r"[\s\-\.]+", " ", cleaned).strip()

    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_phone(
    raw: Optional[str],
    country_hint: Optional[str] = None,
) -> Optional[str]:
    """
    Normalize a raw phone number string to E.164 format.

    Args:
        raw:          The raw phone string.
        country_hint: ISO Alpha-2 region code (e.g. "IN", "US", "GB").
                      MUST be Alpha-2 — not a full country name.

    Returns:
        E.164 string (e.g. "+919876543210") or None if unparseable.
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    cleaned = _preprocess_phone(cleaned)

    # Strategy 1: Try with the provided country hint
    result = _try_parse(cleaned, country_hint)
    if result:
        return result

    # Strategy 2: If no country code and hint failed, try "IN" and "US" as
    # common fallbacks for 10-digit numbers
    digits_only = re.sub(r"\D", "", cleaned)
    if len(digits_only) == 10 and not cleaned.startswith("+"):
        for fallback in ("IN", "US"):
            if fallback != country_hint:
                result = _try_parse(cleaned, fallback)
                if result:
                    logger.debug(
                        "Phone %r matched with fallback region %s → %s",
                        raw, fallback, result
                    )
                    return result

    logger.warning("Could not parse phone number %r (hint=%r)", raw, country_hint)
    return None


def normalize_phones(
    raw_list: list[str],
    country_hint: Optional[str] = None,
) -> list[str]:
    """
    Normalize a list of raw phone strings, dropping invalid ones.
    Returns a deduplicated list of E.164 strings.
    """
    seen:   set[str]   = set()
    result: list[str]  = []

    for raw in raw_list:
        normalised = normalize_phone(raw, country_hint)
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_parse(cleaned: str, region: Optional[str]) -> Optional[str]:
    """
    Attempt to parse and validate a phone string with a given region hint.
    Returns E.164 string or None.
    """
    try:
        parsed = phonenumbers.parse(cleaned, region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        return None
    except (NumberParseException, Exception):
        return None
