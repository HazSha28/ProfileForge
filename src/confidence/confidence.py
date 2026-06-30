"""
src/confidence/confidence.py
----------------------------
WHY THIS FILE EXISTS
----------------------------
A field value is only as trustworthy as the sources that agree on it.
If a phone number appears on the resume AND in the CSV, we are more
confident it is correct than if it only appears in one place.

This module assigns a deterministic numeric score (0.0–1.0) to each field
based on the combination of sources that contributed to it.

PIPELINE CONNECTION
-------------------
  Merger calls calculate() for each field after deciding the final value.
  Input:  set of source names (e.g. {"Resume", "CSV"})
  Output: float confidence score
"""

from __future__ import annotations

from typing import FrozenSet


# ---------------------------------------------------------------------------
# Confidence score table
# ---------------------------------------------------------------------------
# WHY a lookup table instead of a formula?
#   A lookup table is:
#   - Deterministic: same input always yields same output.
#   - Transparent: a new team member can read the business rules directly.
#   - Easy to update: changing a score requires one line, not a formula.
#
# CONCEPT — FrozenSet:
#   A frozenset is an immutable set. We use it as a dict key because:
#   - Regular lists and sets cannot be dict keys (they are mutable).
#   - frozenset({"Resume", "CSV"}) == frozenset({"CSV", "Resume"})
#     so order doesn't matter — which is exactly what we want.
# ---------------------------------------------------------------------------

_SCORE_TABLE: dict[FrozenSet[str], float] = {
    # Single source
    frozenset({"Resume"}):                      0.6,
    frozenset({"CSV"}):                         0.5,

    # Two sources
    frozenset({"Resume", "CSV"}):               0.85,

    # Three sources (future-proof for LinkedIn etc.)
    frozenset({"Resume", "CSV", "LinkedIn"}):   1.0,
    frozenset({"Resume", "LinkedIn"}):          0.9,
    frozenset({"CSV", "LinkedIn"}):             0.8,
}

# Default score when no specific rule exists (e.g. unknown source combo)
_DEFAULT_SCORE = 0.5


def calculate(sources: list[str]) -> float:
    """
    Return a deterministic confidence score for a given set of sources.

    Args:
        sources: List of source names that contributed a value for this field
                 (e.g. ["Resume", "CSV"]).

    Returns:
        Float in range [0.0, 1.0].

    Examples:
        calculate(["Resume"])           -> 0.6
        calculate(["CSV"])              -> 0.5
        calculate(["Resume", "CSV"])    -> 0.85
        calculate([])                   -> 0.0   (no source = no confidence)
        calculate(["Resume", "LinkedIn", "CSV"])  -> 1.0

    CONCEPT — frozenset():
        We convert the list to a frozenset so that:
        1. Order doesn't matter: ["CSV", "Resume"] == ["Resume", "CSV"].
        2. Duplicates are removed: ["Resume", "Resume"] -> {"Resume"}.
    """
    if not sources:
        return 0.0

    key = frozenset(sources)
    return _SCORE_TABLE.get(key, _DEFAULT_SCORE)
