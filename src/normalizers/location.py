"""
src/normalizers/location.py
---------------------------
WHY THIS FILE EXISTS
---------------------------
Country names appear in many forms: "United States", "USA", "us", "U.S.A.".
ISO Alpha-2 ("US") is the machine-readable standard every downstream system
understands. This module converts any recognisable country string to Alpha-2
and trims/title-cases city and region values.

PIPELINE CONNECTION
-------------------
  Called by the Merger after parsing.
  Input:  raw LocationData from CandidateRecord
  Output: normalised LocationData with ISO Alpha-2 country
"""

from __future__ import annotations

from typing import Optional

import pycountry

from src.models.schema import LocationData
from src.utils.helpers import get_logger, safe_strip, safe_title

logger = get_logger(__name__)


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """
    Convert a country name or code to ISO Alpha-2.

    Args:
        raw: Free-form country string (e.g. "United States", "USA", "us").

    Returns:
        ISO Alpha-2 code (e.g. "US") or None if not recognised.

    Examples:
        normalize_country("United States") -> "US"
        normalize_country("deutschland")   -> "DE"
        normalize_country("USA")           -> "US"
        normalize_country("xyz")           -> None  (warning logged)

    WHY pycountry:
        pycountry ships with a complete, up-to-date ISO 3166-1 country
        database. We use its fuzzy search so that "United States",
        "USA", and "US" all resolve correctly.
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    # --- 1. Try exact Alpha-2 lookup first (fast path) ---
    # e.g. "US", "GB" — already in the right format
    upper = cleaned.upper()
    by_alpha2 = pycountry.countries.get(alpha_2=upper)
    if by_alpha2:
        return by_alpha2.alpha_2

    # --- 2. Try exact Alpha-3 lookup (e.g. "USA", "GBR") ---
    by_alpha3 = pycountry.countries.get(alpha_3=upper)
    if by_alpha3:
        return by_alpha3.alpha_2

    # --- 3. Try fuzzy name search (e.g. "United States", "deutschland") ---
    # CONCEPT — try/except:
    #   pycountry.countries.search_fuzzy() raises LookupError when nothing
    #   matches. We catch it and return None rather than letting it crash.
    try:
        results = pycountry.countries.search_fuzzy(cleaned)
        if results:
            return results[0].alpha_2
    except LookupError:
        pass

    logger.warning("Could not map country to ISO Alpha-2: %r", raw)
    return None


def normalize_location(raw: LocationData) -> LocationData:
    """
    Normalize a LocationData object in place.

    - City and region: strip whitespace + title-case.
    - Country: convert to ISO Alpha-2.

    Args:
        raw: LocationData extracted from a parser.

    Returns:
        New LocationData with normalised fields.
    """
    return LocationData(
        city=safe_title(raw.city),
        region=safe_title(raw.region),
        country=normalize_country(raw.country),
    )
