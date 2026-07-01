"""
src/parsers/ai_resume_parser.py
--------------------------------
AI-powered resume extraction via Google Gemini.
Falls back to regex parser on any failure (quota, network, parse error).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from src.models.schema import (
    CandidateRecord,
    ExperienceEntry,
    LinksData,
    LocationData,
)
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Key rotation — cycle through GEMINI_API_KEY, GEMINI_API_KEY_2, _KEY_3
# Each key gets its own fail counter. When one hits quota, next key is tried.
# ---------------------------------------------------------------------------
_key_fail_count: dict[str, int]   = {}
_key_fail_until: dict[str, float] = {}
_MAX_FAILS  = 3
_COOLDOWN   = 600   # 10 minutes per key


def _get_available_keys() -> list[str]:
    """Return all configured Gemini API keys that are not currently in cooldown."""
    now = time.time()
    keys = []
    for env_var in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        key = os.environ.get(env_var, "").strip()
        if not key or key.startswith("your-"):
            continue
        fail_count = _key_fail_count.get(key, 0)
        fail_until = _key_fail_until.get(key, 0.0)
        # Reset counter after cooldown period
        if now >= fail_until:
            _key_fail_count[key] = 0
            fail_count = 0
        if fail_count < _MAX_FAILS:
            keys.append(key)
    return keys


def _record_key_failure(key: str):
    count = _key_fail_count.get(key, 0) + 1
    _key_fail_count[key] = count
    if count >= _MAX_FAILS:
        _key_fail_until[key] = time.time() + _COOLDOWN
        logger.warning("Gemini key ...%s hit quota — cooling down for %dm.", key[-6:], _COOLDOWN // 60)


def _is_circuit_open() -> bool:
    """Returns True only if ALL keys are exhausted."""
    return len(_get_available_keys()) == 0


def _record_failure():
    pass   # kept for backward compat — use _record_key_failure instead

# ---------------------------------------------------------------------------
# Extraction prompt — strict, no hallucination
# ---------------------------------------------------------------------------
_EXTRACTION_PROMPT = """You are an expert Resume Information Extraction Engine.
Your task is ONLY to extract information that explicitly exists in the provided resume text.

Rules:
1. Never hallucinate.
2. Never infer missing values.
3. Never guess.
4. If a field does not exist in the text, return null.
5. Return ONLY valid JSON — no markdown, no explanation, no code fences.
6. Preserve the exact meaning while normalizing obvious formatting inconsistencies.

Extract the following fields from the resume text below:

{
  "full_name": "",
  "emails": [],
  "phones": [],
  "location": {
    "city": "",
    "region": "",
    "country": ""
  },
  "headline": "",
  "summary": "",
  "years_experience": null,
  "skills": [],
  "experience": [
    {
      "company": "",
      "role": "",
      "start_date": "",
      "end_date": "",
      "description": ""
    }
  ],
  "education": [
    {
      "degree": "",
      "institution": "",
      "year": ""
    }
  ],
  "certifications": [],
  "projects": [],
  "github": "",
  "linkedin": "",
  "portfolio": "",
  "other_links": []
}

Rules for skills extraction:
- Include ALL of the following in the "skills" array:
  1. Technical skills: programming languages, frameworks, libraries, tools, databases, cloud platforms
  2. Soft skills: communication, leadership, teamwork, problem solving, time management, etc.
  3. Extracurricular skills: event management, public speaking, volunteering, sports, debate, etc.
  4. Any skill or activity explicitly listed under any section named: Skills, Technical Skills,
     Soft Skills, Core Skills, Tools, Technologies, Extracurricular, Activities, Interests, Strengths
- Extract the skill name exactly as written — do NOT paraphrase or infer
- If a skill is listed under "Soft Skills:" or "Extracurricular:" sub-sections, still include it
- If GitHub, LinkedIn or Portfolio URLs exist anywhere in the resume, extract them.
- Preserve date strings exactly as written in the resume.
- Do not calculate years_experience if it is not explicitly mentioned — return null.
- Do not invent company names.
- Return null for any field that is not present.
- Return ONLY the JSON object. Nothing else.

Resume text:
---
{resume_text}
---"""


def is_available() -> bool:
    """Return True if at least one Gemini key is available and not in cooldown."""
    try:
        from google import genai  # noqa: F401
    except ImportError:
        return False
    return len(_get_available_keys()) > 0


def extract(raw_text: str) -> Optional[CandidateRecord]:
    """
    Extract resume fields via Gemini with automatic key rotation.
    Returns None on all keys exhausted — regex fallback runs automatically.
    """
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed — using regex fallback.")
        return None

    keys = _get_available_keys()
    if not keys:
        logger.info("All Gemini keys exhausted — using regex fallback.")
        return None

    prompt = _EXTRACTION_PROMPT.replace("{resume_text}", raw_text[:12000])

    for api_key in keys:
        logger.info("Trying Gemini key ...%s", api_key[-6:])
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=4096,
                ),
            )

            raw_json = response.text.strip()
            if raw_json.startswith("```"):
                raw_json = raw_json.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]
            raw_json = raw_json.strip()

            data = json.loads(raw_json)
            logger.info("AI extraction succeeded with key ...%s", api_key[-6:])
            return _to_candidate_record(data)

        except json.JSONDecodeError as exc:
            logger.error("AI extraction returned invalid JSON: %s", exc)
            _record_key_failure(api_key)
            continue

        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                logger.warning("Key ...%s quota exceeded — trying next key.", api_key[-6:])
            else:
                logger.error("AI extraction failed: %s", exc)
            _record_key_failure(api_key)
            continue

    logger.warning("All Gemini keys failed — using regex fallback.")
    return None


def _to_candidate_record(data: dict) -> CandidateRecord:
    """Convert the raw extracted dict to a CandidateRecord."""

    def _str(val) -> Optional[str]:
        """Safely convert to string or return None."""
        if val is None or val == "" or val == "null":
            return None
        return str(val).strip() or None

    def _list(val) -> list:
        """Ensure value is a list of non-empty strings."""
        if not val or not isinstance(val, list):
            return []
        return [str(v).strip() for v in val if v and str(v).strip()]

    # --- Location ---
    loc_raw = data.get("location") or {}
    location = LocationData(
        city    = _str(loc_raw.get("city")),
        region  = _str(loc_raw.get("region")),
        country = _str(loc_raw.get("country")),
    )

    # --- Links ---
    other_links = _list(data.get("other_links"))
    links = LinksData(
        linkedin  = _str(data.get("linkedin")),
        github    = _str(data.get("github")),
        portfolio = _str(data.get("portfolio")),
        other     = other_links,
    )

    # --- Experience entries ---
    experience: list[ExperienceEntry] = []
    for exp in (data.get("experience") or []):
        if not isinstance(exp, dict):
            continue
        experience.append(ExperienceEntry(
            company     = _str(exp.get("company")),
            title       = _str(exp.get("role")),
            start_date  = _str(exp.get("start_date")),
            end_date    = _str(exp.get("end_date")),
            description = _str(exp.get("description")),
        ))

    # --- Years experience ---
    yrs_raw = data.get("years_experience")
    years_experience: Optional[int] = None
    if yrs_raw is not None:
        try:
            years_experience = int(float(str(yrs_raw)))
        except (ValueError, TypeError):
            years_experience = None

    # --- Headline: prefer headline, fall back to summary first line ---
    headline = _str(data.get("headline"))
    if not headline:
        summary = _str(data.get("summary"))
        if summary:
            headline = summary.split(".")[0].strip()

    return CandidateRecord(
        source           = "Resume",
        full_name        = _str(data.get("full_name")),
        emails           = _list(data.get("emails")),
        phones           = _list(data.get("phones")),
        location         = location,
        links            = links,
        headline         = headline,
        years_experience = years_experience,
        skills           = _list(data.get("skills")),
        experience       = experience,
    )
