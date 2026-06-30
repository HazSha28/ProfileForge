"""
src/validator/validator.py
--------------------------
WHY THIS FILE EXISTS
--------------------------
Before writing the final JSON, we need to verify that the profile meets
minimum quality standards: required fields are present, emails look like
emails, phones look like E.164. This module collects ALL issues rather
than crashing on the first one — so operators see the full picture.

PIPELINE CONNECTION
-------------------
  merger → CanonicalProfile → validate() → (CanonicalProfile, [warnings])
  The caller (main.py) decides whether to abort or proceed with warnings.
"""

from __future__ import annotations

import re
from typing import Tuple

from src.models.schema import CanonicalProfile
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Format patterns (same as normalizers, but used here for final check)
# ---------------------------------------------------------------------------
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_E164_REGEX  = re.compile(r"^\+[1-9]\d{6,14}$")

# Fields that MUST be present and non-null for the profile to be useful
_REQUIRED_FIELDS = ["full_name"]


def validate(profile: CanonicalProfile) -> Tuple[CanonicalProfile, list[str]]:
    """
    Validate a CanonicalProfile and return it alongside any warnings.

    Validation never mutates the profile and never raises an exception.
    Instead, every problem is collected into `warnings` and returned so
    the caller can decide what to do.

    Args:
        profile: The merged CanonicalProfile to validate.

    Returns:
        Tuple of (profile, warnings) where warnings is a list of strings
        describing every validation issue found. An empty list means clean.

    CONCEPT — Tuple return:
        Returning (profile, warnings) lets the caller get both the data
        AND the issues in one call without relying on side effects.
    """
    warnings: list[str] = []

    # --- 1. Required fields ---
    for field_name in _REQUIRED_FIELDS:
        fv = getattr(profile, field_name, None)
        if fv is None or fv.value is None:
            msg = f"Required field '{field_name}' is missing or null."
            warnings.append(msg)
            logger.warning(msg)

    # --- 2. candidate_id ---
    if not profile.candidate_id:
        msg = "Field 'candidate_id' is empty."
        warnings.append(msg)
        logger.warning(msg)

    # --- 3. Email format validation ---
    emails = profile.emails.value or []
    for email in emails:
        if not _EMAIL_REGEX.match(str(email)):
            msg = f"Email '{email}' does not match expected format."
            warnings.append(msg)
            logger.warning(msg)

    # --- 4. Phone E.164 format validation ---
    phones = profile.phones.value or []
    for phone in phones:
        if not _E164_REGEX.match(str(phone)):
            msg = f"Phone '{phone}' is not in E.164 format."
            warnings.append(msg)
            logger.warning(msg)

    # --- 5. years_experience sanity check ---
    years = profile.years_experience.value
    if years is not None:
        if not isinstance(years, (int, float)) or years < 0 or years > 60:
            msg = f"years_experience value '{years}' is outside expected range [0, 60]."
            warnings.append(msg)
            logger.warning(msg)

    if not warnings:
        logger.info("Validation passed with no warnings.")
    else:
        logger.warning("Validation completed with %d warning(s).", len(warnings))

    return profile, warnings
