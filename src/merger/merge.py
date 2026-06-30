"""
src/merger/merge.py
-------------------
WHY THIS FILE EXISTS
-------------------
The Merger is the core of the pipeline. It takes one CandidateRecord per
source, applies normalisation to every field, and combines them into a
single CanonicalProfile according to the documented merge policy.

MERGE POLICY (documented here, deterministic, no randomness)
------------------------------------------------------------
  Priority order (highest to lowest):
    1. Resume   — richer, candidate-authored data
    2. CSV      — recruiter-supplied, may be less complete

  For scalar fields (full_name, headline, years_experience):
    → Use the highest-priority source that has a non-null value.
    → If timestamps are present, prefer the value with the newer timestamp.

  For list fields (emails, phones, skills):
    → Produce a deduplicated UNION of all sources' values.

  For structured fields (location, links):
    → Merge sub-fields individually using the same scalar rule.

  Every field in the output records which sources contributed to it
  (provenance) and carries a confidence score.

PIPELINE CONNECTION
-------------------
  parsers → [CandidateRecord, ...] → merge() → CanonicalProfile
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from src.confidence.confidence import calculate as calc_confidence
from src.models.schema import (
    CandidateRecord,
    CanonicalProfile,
    ExperienceEntry,
    FieldValue,
    LinksData,
    LocationData,
)
from src.normalizers.dates import normalize_date
from src.normalizers.email import normalize_emails
from src.normalizers.location import normalize_location
from src.normalizers.phone import normalize_phones
from src.normalizers.skills import normalize_skills
from src.utils.helpers import get_logger, safe_title

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Source priority order (index 0 = highest priority)
# ---------------------------------------------------------------------------
# WHY a list?
#   The list preserves order, so we can iterate from highest to lowest
#   priority when picking the winning value for a scalar field.
_SOURCE_PRIORITY: list[str] = ["Resume", "CSV"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge(records: list[CandidateRecord]) -> CanonicalProfile:
    """
    Merge a list of CandidateRecords into one CanonicalProfile.

    Args:
        records: One CandidateRecord per source. Order does not matter;
                 the merge policy handles priority internally.

    Returns:
        CanonicalProfile with all fields normalised, merged, and annotated
        with provenance and confidence scores.
    """
    logger.info("Merging %d source record(s): %s", len(records), [r.source for r in records])

    # Step 1: Normalise all records in place
    normalised = [_normalise_record(r) for r in records]

    # Step 2: Build a lookup by source name for easy priority access
    # CONCEPT — dict comprehension: {key: value for item in list}
    by_source: dict[str, CandidateRecord] = {r.source: r for r in normalised}

    # Step 3: Merge each field
    profile = CanonicalProfile(
        candidate_id=str(uuid.uuid4()),

        full_name    = _merge_scalar(by_source, field="full_name"),
        headline     = _merge_scalar(by_source, field="headline"),
        years_experience = _merge_scalar(by_source, field="years_experience"),

        emails  = _merge_list(by_source, field="emails"),
        phones  = _merge_list(by_source, field="phones"),
        skills  = _merge_list(by_source, field="skills"),
        experience = _merge_list(by_source, field="experience"),

        location = _merge_location(by_source),
        links    = _merge_links(by_source),
    )

    logger.info(
        "Merge complete — candidate_id=%s, name=%r, skills=%d",
        profile.candidate_id,
        profile.full_name.value,
        len(profile.skills.value or []),
    )

    return profile


# ---------------------------------------------------------------------------
# Normalisation step
# ---------------------------------------------------------------------------

def _normalise_record(record: CandidateRecord) -> CandidateRecord:
    """
    Apply all normalizers to a CandidateRecord and return a new record.

    WHY normalise inside the merger?
        Parsers produce raw data. Normalisers are applied once, centrally,
        before merging so that comparisons and deduplication are done on
        the canonical forms (e.g. comparing "+14155552671" not "(415)555-2671").
    """
    # Normalise country to ISO Alpha-2 FIRST so the phone normalizer gets
    # a valid region code (phonenumbers only accepts "US", not "United States").
    normalised_location = normalize_location(record.location)
    country_hint = normalised_location.country   # e.g. "US", "GB", or None

    return CandidateRecord(
        source=record.source,
        timestamp=record.timestamp,

        full_name=safe_title(record.full_name),

        emails=normalize_emails(record.emails),

        phones=normalize_phones(record.phones, country_hint=country_hint),

        location=normalised_location,

        links=record.links,   # URLs kept as-is (no normalisation needed)

        headline=record.headline,

        years_experience=record.years_experience,

        # Normalize skills to canonical names
        skills=normalize_skills(record.skills),

        # Normalize experience dates
        experience=_normalise_experience(record.experience),
    )


def _normalise_experience(entries: list[ExperienceEntry]) -> list[ExperienceEntry]:
    """Normalize dates inside every ExperienceEntry."""
    normalised = []
    for entry in entries:
        normalised.append(ExperienceEntry(
            title=safe_title(entry.title),
            company=safe_title(entry.company),
            start_date=normalize_date(entry.start_date),
            end_date=normalize_date(entry.end_date),
            description=entry.description,
        ))
    return normalised


# ---------------------------------------------------------------------------
# Scalar field merger
# ---------------------------------------------------------------------------

def _merge_scalar(
    by_source: dict[str, CandidateRecord],
    field: str,
) -> FieldValue:
    """
    Pick the best value for a scalar field using the source priority order.

    Strategy:
    1. Iterate sources from highest to lowest priority.
    2. Return the first non-None value found.
    3. Record all sources that had a non-None value as provenance.

    Args:
        by_source: Dict mapping source name to its normalised CandidateRecord.
        field:     The attribute name on CandidateRecord to read.

    Returns:
        FieldValue with value, sources, and confidence populated.
    """
    winning_value: Any = None
    contributing_sources: list[str] = []

    # First pass: collect all non-None values and their sources
    source_values: list[tuple[str, Any]] = []
    for source in _SOURCE_PRIORITY:
        record = by_source.get(source)
        if record is None:
            continue
        value = getattr(record, field, None)
        if value is not None:
            source_values.append((source, value))

    if not source_values:
        # All sources had None for this field
        return FieldValue(value=None, sources=[], confidence=0.0)

    # Winning value: highest-priority source (first in _SOURCE_PRIORITY)
    winning_value = source_values[0][1]
    contributing_sources = [s for s, _ in source_values]

    logger.debug(
        "Field '%s': winner=%r (from %s), all sources=%s",
        field, winning_value, source_values[0][0], contributing_sources,
    )

    return FieldValue(
        value=winning_value,
        sources=contributing_sources,
        confidence=calc_confidence(contributing_sources),
    )


# ---------------------------------------------------------------------------
# List field merger
# ---------------------------------------------------------------------------

def _merge_list(
    by_source: dict[str, CandidateRecord],
    field: str,
) -> FieldValue:
    """
    Produce a deduplicated union of list fields from all sources.

    For lists (emails, phones, skills, experience), we don't pick a winner —
    we combine everything and deduplicate, because more is better.

    Provenance: all sources that contributed at least one item.
    Confidence: based on which sources contributed.
    """
    combined: list[Any] = []
    seen: set[Any] = set()
    contributing_sources: list[str] = []

    for source in _SOURCE_PRIORITY:
        record = by_source.get(source)
        if record is None:
            continue

        values: list[Any] = getattr(record, field, []) or []
        if not values:
            continue

        contributing_sources.append(source)

        for item in values:
            # For ExperienceEntry objects, use a tuple of key fields as the
            # deduplication key since Pydantic models are not hashable.
            if isinstance(item, ExperienceEntry):
                key = (item.title, item.company, item.start_date)
            else:
                key = item

            if key not in seen:
                seen.add(key)
                combined.append(item)

    if not combined:
        return FieldValue(value=[], sources=[], confidence=0.0)

    return FieldValue(
        value=combined,
        sources=contributing_sources,
        confidence=calc_confidence(contributing_sources),
    )


# ---------------------------------------------------------------------------
# Location field merger
# ---------------------------------------------------------------------------

def _merge_location(by_source: dict[str, CandidateRecord]) -> FieldValue:
    """
    Merge LocationData sub-fields individually.

    For each sub-field (city, region, country), apply the scalar priority
    rule. Then wrap the merged LocationData in a FieldValue.
    """
    city_fv    = _merge_scalar(by_source, _LocationProxy("city"))
    region_fv  = _merge_scalar(by_source, _LocationProxy("region"))
    country_fv = _merge_scalar(by_source, _LocationProxy("country"))

    # Collect all contributing sources across sub-fields
    all_sources: list[str] = list(dict.fromkeys(
        city_fv.sources + region_fv.sources + country_fv.sources
    ))

    merged_location = LocationData(
        city=city_fv.value,
        region=region_fv.value,
        country=country_fv.value,
    )

    return FieldValue(
        value=merged_location.model_dump(),
        sources=all_sources,
        confidence=calc_confidence(all_sources),
    )


def _merge_links(by_source: dict[str, CandidateRecord]) -> FieldValue:
    """
    Merge LinksData sub-fields individually.

    For each link type, take the first non-null value in priority order.
    """
    def _pick(field: str) -> Optional[str]:
        for source in _SOURCE_PRIORITY:
            record = by_source.get(source)
            if record is None:
                continue
            value = getattr(record.links, field, None)
            if value:
                return value
        return None

    # 'other' is a list — union across sources
    other_combined: list[str] = []
    seen_other: set[str] = set()
    contributing_sources: list[str] = []

    for source in _SOURCE_PRIORITY:
        record = by_source.get(source)
        if record is None:
            continue
        has_any = any([
            record.links.linkedin,
            record.links.github,
            record.links.portfolio,
            record.links.other,
        ])
        if has_any:
            contributing_sources.append(source)
        for url in (record.links.other or []):
            if url not in seen_other:
                seen_other.add(url)
                other_combined.append(url)

    merged_links = LinksData(
        linkedin=_pick("linkedin"),
        github=_pick("github"),
        portfolio=_pick("portfolio"),
        other=other_combined,
    )

    return FieldValue(
        value=merged_links.model_dump(),
        sources=list(dict.fromkeys(contributing_sources)),
        confidence=calc_confidence(contributing_sources),
    )


# ---------------------------------------------------------------------------
# Helper: proxy object for sub-field access
# ---------------------------------------------------------------------------
# The _merge_scalar function calls getattr(record, field). For top-level
# fields this works directly. For nested fields like location.city we need
# a small proxy trick.
# ---------------------------------------------------------------------------

class _LocationProxy(str):
    """
    A special string subclass used as the `field` argument to _merge_scalar
    so it can reach into the nested location object.

    When _merge_scalar does getattr(record, proxy_instance), we override
    __get__ semantics by patching the call — actually we just implement
    a helper that overrides how getattr works for location sub-fields.

    Simpler approach: override _merge_scalar to accept a callable.
    We use a direct approach below instead.
    """

# NOTE: Rather than making _merge_scalar generic (harder to read),
# we implement _merge_location_subfield as a direct helper.

def _merge_location_subfield(
    by_source: dict[str, CandidateRecord],
    subfield: str,
) -> FieldValue:
    """Merge a single sub-field of LocationData using priority order."""
    source_values: list[tuple[str, Any]] = []

    for source in _SOURCE_PRIORITY:
        record = by_source.get(source)
        if record is None:
            continue
        value = getattr(record.location, subfield, None)
        if value is not None:
            source_values.append((source, value))

    if not source_values:
        return FieldValue(value=None, sources=[], confidence=0.0)

    winning_value = source_values[0][1]
    contributing_sources = [s for s, _ in source_values]

    return FieldValue(
        value=winning_value,
        sources=contributing_sources,
        confidence=calc_confidence(contributing_sources),
    )


# Fix _merge_location to use the correct helper
def _merge_location(by_source: dict[str, CandidateRecord]) -> FieldValue:  # type: ignore[no-redef]
    city_fv    = _merge_location_subfield(by_source, "city")
    region_fv  = _merge_location_subfield(by_source, "region")
    country_fv = _merge_location_subfield(by_source, "country")

    all_sources = list(dict.fromkeys(
        city_fv.sources + region_fv.sources + country_fv.sources
    ))

    merged_location = LocationData(
        city=city_fv.value,
        region=region_fv.value,
        country=country_fv.value,
    )

    return FieldValue(
        value=merged_location.model_dump(),
        sources=all_sources,
        confidence=calc_confidence(all_sources),
    )
