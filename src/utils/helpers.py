"""
src/utils/helpers.py
--------------------
WHY THIS FILE EXISTS
--------------------
Small, reusable utility functions that don't belong to any single module
but are needed across the whole pipeline. Keeping them here prevents code
duplication and makes them easy to test in isolation.

PIPELINE CONNECTION
-------------------
  Imported by parsers, normalizers, merger, and the CLI entry point.
  Nothing in the pipeline imports FROM the pipeline INTO this file —
  helpers are a "leaf" module with no internal dependencies.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
# WHY: Having one central place that configures logging means every module
# gets the same format, the same destination (stderr), and the same level
# just by calling `get_logger(__name__)`. If we ever need to change the
# log format, we change it in one place.
#
# CONCEPT — __name__:
#   In Python, `__name__` is a built-in variable that holds the name of
#   the current module (e.g. "src.parsers.csv_parser"). Using it as the
#   logger name means log messages automatically say which module they
#   came from, which makes debugging much easier.
#
# CONCEPT — stderr vs stdout:
#   Log messages go to stderr (sys.stderr) so that they don't mix with
#   the actual program output (the JSON) which goes to stdout/file.
# ---------------------------------------------------------------------------

def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for the given module name.

    Usage in any module:
        from src.utils.helpers import get_logger
        logger = get_logger(__name__)
        logger.info("Starting parse...")
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called multiple times
    # for the same name (can happen during testing).
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    return logger


# ---------------------------------------------------------------------------
# Safe string helpers
# ---------------------------------------------------------------------------

def safe_strip(value: Optional[str]) -> Optional[str]:
    """
    Strip whitespace from a string and return None if the result is empty.

    WHY: Parsers often get fields like "  " from CSV cells. We never want
    empty-string values flowing through the pipeline — None is our explicit
    signal for "no data".

    Example:
        safe_strip("  hello  ") -> "hello"
        safe_strip("   ")       -> None
        safe_strip(None)        -> None
    """
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def safe_lower(value: Optional[str]) -> Optional[str]:
    """
    Lowercase a string safely, returning None if the input is None or empty.

    Example:
        safe_lower("Hello@Example.COM") -> "hello@example.com"
        safe_lower(None)                -> None
    """
    stripped = safe_strip(value)
    return stripped.lower() if stripped else None


def safe_title(value: Optional[str]) -> Optional[str]:
    """
    Apply title-case to a string safely.

    WHY: Candidate names and city names should be consistently capitalised
    regardless of how the source provided them ("john doe" -> "John Doe").

    Example:
        safe_title("john doe")   -> "John Doe"
        safe_title("NEW YORK")   -> "New York"
        safe_title(None)         -> None
    """
    stripped = safe_strip(value)
    return stripped.title() if stripped else None
