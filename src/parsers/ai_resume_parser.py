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
# Circuit breaker — if Gemini fails 3 times, skip it for 10 minutes
# ---------------------------------------------------------------------------
_fail_count = 0
_fail_until = 0.0
_MAX_FAILS   = 3
_COOLDOWN    = 600   # 10 minutes


def _is_circuit_open() -> bool:
    global _fail_count, _fail_until
    if _fail_count >= _MAX_FAILS and time.time() < _fail_until:
        logger.info("Gemini circuit breaker open — using regex fallback.")
        return True
    if time.time() >= _fail_until:
        _fail_count = 0   # reset after cooldown
    return False


def _record_failure():
    global _fail_count, _fail_until
    _fail_count += 1
    if _fail_count >= _MAX_FAILS:
        _fail_until = time.time() + _COOLDOWN
        logger.warning(
            "Gemini failed %d times — switching to regex for %d minutes.",
            _fail_count, _COOLDOWN // 60
        )

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
def is_available() -> bool:
    """Return True if Gemini is configured, installed, and circuit is closed."""
    if _is_circuit_open():
        return False
    if not os.environ.get("GEMINI_API_KEY"):
        return False
    try:
        from google import genai  # noqa: F401
        return True
    except ImportError:
        return False


def extract(raw_text: str) -> Optional[CandidateRecord]:
    """
    Extract resume fields via Gemini. Returns None on any failure so
    resume_parser.py falls back to regex automatically.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or _is_circuit_open():
        return None

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed — using regex fallback.")
        return None

    logger.info("Running AI resume extraction via Gemini...")

    try:
        client = genai.Client(api_key=api_key)
        prompt = _EXTRACTION_PROMPT.replace("{resume_text}", raw_text[:12000])

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
        logger.info("AI extraction succeeded.")
        return _to_candidate_record(data)

    except json.JSONDecodeError as exc:
        logger.error("AI extraction returned invalid JSON: %s", exc)
        _record_failure()
        return None
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
            logger.warning("Gemini quota exceeded — falling back to regex.")
        else:
            logger.error("AI extraction failed: %s", exc)
        _record_failure()
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
