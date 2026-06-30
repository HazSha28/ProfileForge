"""
src/models/schema.py
--------------------
WHY THIS FILE EXISTS
--------------------
Every module in the pipeline passes data to the next. Without a shared,
enforced data shape, modules make assumptions about each other and bugs
become very hard to trace. This file defines the *contracts* — the exact
structure every piece of data must have at every stage of the pipeline.

We use Pydantic (v2) for this. Pydantic does two things at once:
  1. It documents the shape of your data (like a schema).
  2. It validates that data at runtime — if you try to put the wrong type
     in a field, it raises an error immediately, telling you exactly where
     the problem is.

PIPELINE CONNECTION
-------------------
  Parsers       → produce CandidateRecord
  Normalizers   → operate on raw string fields inside CandidateRecord
  Merger        → takes List[CandidateRecord], produces CanonicalProfile
  Validator     → validates CanonicalProfile against this schema
  Projector     → reads CanonicalProfile, writes filtered output JSON
"""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# FieldValue
# ---------------------------------------------------------------------------
# WHY: A raw string like "Python" doesn't tell you where it came from or
# how confident you should be in it. FieldValue wraps any value with that
# metadata. Every meaningful field in the canonical profile is a FieldValue.
#
# CONCEPT — Generic typing with `Any`:
#   The `value` field is typed as `Any` because different fields hold
#   different types: a name is a str, years_experience is an int, skills
#   is a list. Using Any lets one class cover all cases cleanly.
# ---------------------------------------------------------------------------

class FieldValue(BaseModel):
    """A field value paired with its provenance and confidence score."""

    value: Any = None
    """The actual data value (str, int, list, dict, etc.)."""

    sources: List[str] = Field(default_factory=list)
    """Which source(s) this value came from. E.g. ['Resume', 'CSV']."""

    confidence: float = 0.0
    """Deterministic confidence score in range [0.0, 1.0]."""


# ---------------------------------------------------------------------------
# LocationData
# ---------------------------------------------------------------------------
# WHY: Location has sub-fields (city, region, country). Keeping them
# grouped in their own model makes them easy to pass around and validate
# together. It mirrors the output schema exactly.
# ---------------------------------------------------------------------------

class LocationData(BaseModel):
    """Parsed location broken into components."""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None  # Will be normalised to ISO Alpha-2


# ---------------------------------------------------------------------------
# LinksData
# ---------------------------------------------------------------------------
# WHY: Candidates have multiple URL types. A dedicated model prevents the
# merger from having to know which keys to look for — it just merges a
# LinksData object.
# ---------------------------------------------------------------------------

class LinksData(BaseModel):
    """URLs extracted from candidate sources."""
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    other: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ExperienceEntry
# ---------------------------------------------------------------------------
# WHY: Work experience is a list of structured objects, not just strings.
# Defining the shape here means the resume parser and merger agree on
# exactly what an "experience entry" looks like.
# ---------------------------------------------------------------------------

class ExperienceEntry(BaseModel):
    """A single work experience record."""
    title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None   # ISO 8601: YYYY-MM-DD
    end_date: Optional[str] = None     # ISO 8601 or "Present"
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# CandidateRecord
# ---------------------------------------------------------------------------
# WHY: This is the *intermediate* representation — the raw data extracted
# from exactly ONE source before merging. Both the CSV parser and the
# Resume parser produce a CandidateRecord. They don't know about each
# other; they just fill in this shared shape.
#
# CONCEPT — Optional[str]:
#   `Optional[str]` means the field can be either a str or None. This
#   is shorthand for `Union[str, None]`. We use it everywhere because a
#   parser might not find every field — and that's fine; `None` is the
#   explicit signal for "not found".
# ---------------------------------------------------------------------------

class CandidateRecord(BaseModel):
    """
    Raw candidate data extracted from a single source.

    Each parser produces one of these. Fields that the source does not
    contain are left as None — never raise an exception for missing data.
    """

    source: str
    """Name of the source that produced this record. E.g. 'CSV' or 'Resume'."""

    full_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    location: LocationData = Field(default_factory=LocationData)
    links: LinksData = Field(default_factory=LinksData)
    headline: Optional[str] = None
    years_experience: Optional[int] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)

    # Raw timestamp from the source if available (used in merge tie-breaking)
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# CanonicalProfile
# ---------------------------------------------------------------------------
# WHY: This is the *final* output shape. Every field is a FieldValue so
# that consumers always have access to provenance and confidence alongside
# the actual value. This is what gets written to output/candidate.json.
# ---------------------------------------------------------------------------

class CanonicalProfile(BaseModel):
    """
    The fully merged, normalised, and annotated candidate profile.

    Each field is wrapped in FieldValue to preserve provenance and confidence.
    This is the shape validated by the Validator and projected by the Projector.
    """

    candidate_id: str = ""
    """UUID v4 generated at merge time."""

    full_name: FieldValue = Field(default_factory=FieldValue)
    emails: FieldValue = Field(default_factory=FieldValue)
    phones: FieldValue = Field(default_factory=FieldValue)
    location: FieldValue = Field(default_factory=FieldValue)
    links: FieldValue = Field(default_factory=FieldValue)
    headline: FieldValue = Field(default_factory=FieldValue)
    years_experience: FieldValue = Field(default_factory=FieldValue)
    skills: FieldValue = Field(default_factory=FieldValue)
    experience: FieldValue = Field(default_factory=FieldValue)
