"""
src/parsers/ai_resume_parser.py
--------------------------------
WHY THIS FILE EXISTS
--------------------
The regex-based resume parser works for well-formatted PDFs but misses fields
in unusual layouts. This module sends the raw PDF text to Google Gemini with
a strict extraction prompt — the LLM finds every field regardless of layout,
and is explicitly instructed never to hallucinate or infer missing data.

PIPELINE CONNECTION
-------------------
  resume_parser.py calls this module when GEMINI_API_KEY is present.
  Falls back to the regex parser when the key is absent or the API fails.

  PDF text → Gemini API → strict JSON → CandidateRecord
"""

from __future__ import annotations

import json
import os
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

Rules:
- Skills must only contain technologies explicitly mentioned in the text.
- If GitHub, LinkedIn or Portfolio URLs exist anywhere in the resume, extract them.
- Preserve date strings exactly as written in the resume.
- Do not calculate years_experience if it is not explicitly mentioned — return null.
- Do not invent company names.
- Do not infer skills from job descriptions unless they are explicitly listed.
- Return null for any field that is not present.
- Return ONLY the JSON object. Nothing else.

Resume text:
---
{resume_text}
---"""


def is_available() -> bool:
    """Return True if a Gemini API key is configured."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def extract(raw_text: str) -> Optional[CandidateRecord]:
    """
    Send resume text to Gemini and parse the structured JSON response
    into a CandidateRecord.

    Args:
        raw_text: Full text extracted from the PDF by pdfplumber.

    Returns:
        CandidateRecord with source="Resume" or None if extraction fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping AI extraction.")
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai not installed — skipping AI extraction.")
        return None

    logger.info("Running AI resume extraction via Gemini...")

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = _EXTRACTION_PROMPT.replace("{resume_text}", raw_text[:12000])

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,        # deterministic — no creativity
                max_output_tokens=4096,
            ),
        )

        raw_json = response.text.strip()

        # Strip markdown code fences if Gemini added them despite instructions
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
        return None
    except Exception as exc:
        logger.error("AI extraction failed: %s", exc)
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
