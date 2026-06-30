"""
src/projection/projector.py
---------------------------
WHY THIS FILE EXISTS
---------------------------
Different downstream systems need different field names or subsets of the
profile. Without this module, every integration would require code changes.
Instead, a config.json file controls what appears in the output — no code
change needed.

PIPELINE CONNECTION
-------------------
  validator → CanonicalProfile → project(profile, config) → dict (→ JSON)

CONFIG FORMAT (config.json)
---------------------------
{
  "include": ["full_name", "emails", "skills"],   // only these fields
  "exclude": ["experience"],                       // drop these fields
  "rename":  {"full_name": "name", "emails": "email_addresses"},
  "missing_value": null                            // substitute for null fields
}

Rules applied in order:
  1. Start with all fields.
  2. If "include" is specified, keep only those fields.
  3. If "exclude" is specified, drop those fields.
  4. Apply "rename" mappings.
  5. Substitute "missing_value" for any null field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.models.schema import CanonicalProfile
from src.utils.helpers import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str]) -> dict:
    """
    Load and parse a config.json file.

    Returns an empty dict (default projection) if the path is None,
    the file is missing, or the file is malformed.
    """
    if not config_path:
        return {}

    path = Path(config_path)
    if not path.exists():
        logger.warning("Config file not found: %s — using default projection.", config_path)
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
        logger.info("Loaded projection config from %s", config_path)
        return config
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse config file %s: %s — using default projection.", config_path, exc)
        return {}


# ---------------------------------------------------------------------------
# Projector
# ---------------------------------------------------------------------------

def project(profile: CanonicalProfile, config: dict) -> dict:
    """
    Convert a CanonicalProfile to a plain dict, applying config projections.

    The output dict is what gets serialised to output/candidate.json.

    Args:
        profile: The validated CanonicalProfile.
        config:  Parsed contents of config.json (may be empty dict).

    Returns:
        A plain Python dict ready for json.dumps().
    """
    include_fields: Optional[list[str]] = config.get("include")
    exclude_fields: list[str]           = config.get("exclude", [])
    rename_map: dict[str, str]          = config.get("rename", {})
    missing_value: Any                  = config.get("missing_value", None)

    # --- Step 1: Serialise the full profile to a dict ---
    raw = _serialise_profile(profile)

    # --- Step 2: Apply include filter ---
    if include_fields:
        # Always keep candidate_id even if not listed — it's the record key
        keep = set(include_fields) | {"candidate_id"}
        raw = {k: v for k, v in raw.items() if k in keep}

    # --- Step 3: Apply exclude filter ---
    for field in exclude_fields:
        raw.pop(field, None)

    # --- Step 4: Apply rename mapping ---
    for old_name, new_name in rename_map.items():
        if old_name in raw:
            raw[new_name] = raw.pop(old_name)

    # --- Step 5: Substitute missing_value for nulls ---
    if missing_value is not None:
        raw = _substitute_nulls(raw, missing_value)

    return raw


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serialise_profile(profile: CanonicalProfile) -> dict:
    """
    Convert a CanonicalProfile to a nested dict suitable for JSON output.

    Each FieldValue becomes: {"value": ..., "sources": [...], "confidence": ...}

    CONCEPT — model_dump():
        Pydantic v2 provides model_dump() which converts a model instance
        to a plain Python dict. We call it on each FieldValue and on
        nested Pydantic models (LocationData, LinksData).
    """
    def fv_to_dict(fv) -> dict:
        """Expand a FieldValue to its three-key representation."""
        value = fv.value
        # If value is a Pydantic model, dump it to a plain dict
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        # If value is a list of Pydantic models, dump each
        if isinstance(value, list):
            value = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in value
            ]
        return {
            "value": value,
            "sources": fv.sources,
            "confidence": fv.confidence,
        }

    return {
        "candidate_id": profile.candidate_id,
        "full_name":         fv_to_dict(profile.full_name),
        "emails":            fv_to_dict(profile.emails),
        "phones":            fv_to_dict(profile.phones),
        "location":          fv_to_dict(profile.location),
        "links":             fv_to_dict(profile.links),
        "headline":          fv_to_dict(profile.headline),
        "years_experience":  fv_to_dict(profile.years_experience),
        "skills":            fv_to_dict(profile.skills),
        "experience":        fv_to_dict(profile.experience),
    }


def _substitute_nulls(data: Any, substitute: Any) -> Any:
    """
    Recursively replace None values in a nested dict/list with `substitute`.

    CONCEPT — recursion:
        The output is a nested structure (dicts containing dicts, lists).
        Recursion is the natural way to walk an arbitrarily deep structure
        without knowing its depth in advance.
    """
    if isinstance(data, dict):
        return {
            k: _substitute_nulls(v, substitute) for k, v in data.items()
        }
    if isinstance(data, list):
        return [_substitute_nulls(item, substitute) for item in data]
    if data is None:
        return substitute
    return data
