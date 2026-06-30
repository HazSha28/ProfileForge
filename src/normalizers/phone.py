"""
src/normalizers/phone.py
------------------------
WHY THIS FILE EXISTS
------------------------
Phone numbers appear in dozens of formats: "(415) 555-2671", "415-555-2671",
"+1 415 555 2671", "4155552671". E.164 (+14155552671) is the one format
all telephony systems understand. This module converts anything recognisable
into E.164 and discards the rest.

PIPELINE CONNECTION
-------------------
  Called by the Merger after parsing, before deduplication.
  Input:  raw phone string + optional country hint (ISO Alpha-2)
  Output: E.164 phone string, or None if invalid/unrecognised
"""

from __future__ import annotations

from typing import Optional

import phonenumbers
from phonenumbers import NumberParseException

from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)


def normalize_phone(
    raw: Optional[str],
    country_hint: Optional[str] = None,
) -> Optional[str]:
    """
    Normalize a raw phone number string to E.164 format.

    Args:
        raw:          The raw phone string (e.g. "(415) 555-2671").
        country_hint: ISO Alpha-2 country code to use when the number has
                      no country prefix (e.g. "US", "GB"). This comes from
                      the location field of the same record.

    Returns:
        E.164 formatted phone string (e.g. "+14155552671") or None.

    Examples:
        normalize_phone("(415) 555-2671", "US")  -> "+14155552671"
        normalize_phone("+44 20 7946 0958")       -> "+442079460958"
        normalize_phone("not-a-phone")             -> None  (warning logged)

    WHY phonenumbers library:
        The `phonenumbers` library (a Python port of Google's libphonenumber)
        handles every international format and country prefix rule. Writing
        this logic ourselves would take weeks and still be incomplete.
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    try:
        # CONCEPT — default_region:
        #   If the number has no country code (e.g. "415-555-2671") the parser
        #   needs a hint about which country's numbering plan to apply.
        #   We pass `country_hint` (e.g. "US") as the default_region.
        #   If no hint is available, we pass None and the library will still
        #   try its best with fully international numbers.
        parsed = phonenumbers.parse(cleaned, country_hint)

        if not phonenumbers.is_valid_number(parsed):
            logger.warning("Phone number is not valid, skipping: %r", raw)
            return None

        # PhoneNumberFormat.E164 produces the +countrycode+number format
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    except NumberParseException as exc:
        logger.warning("Could not parse phone number %r: %s", raw, exc)
        return None


def normalize_phones(
    raw_list: list[str],
    country_hint: Optional[str] = None,
) -> list[str]:
    """
    Normalize a list of raw phone strings, dropping any that are invalid.

    Args:
        raw_list:     List of raw phone strings.
        country_hint: ISO Alpha-2 country hint applied to all numbers.

    Returns:
        Deduplicated list of valid E.164 phone strings.
    """
    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_list:
        normalised = normalize_phone(raw, country_hint)
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)

    return result
