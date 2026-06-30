"""
src/services/pipeline.py
------------------------
WHY THIS FILE EXISTS
--------------------
This is the Orchestration Layer — the most important architectural addition
to ProfileForge. It sits between the API router and the individual pipeline
modules, coordinating every step and reporting real-time progress.

DESIGN PATTERN: Service Layer
  API Router → PipelineService → (parsers, normalizers, merger, validator, projector)

WHY a service layer instead of calling modules directly from the router?
  1. Single Responsibility: the router handles HTTP, the service handles business logic.
  2. Testability: you can test the full pipeline without a running HTTP server.
  3. Reusability: both the single-candidate API and the bulk API use the same service.
  4. Progress streaming: the service emits step-by-step events the frontend consumes.

CONCEPT — Python Generators (yield):
  The `run()` method is a generator function — it uses `yield` to emit
  progress events one at a time as each pipeline step completes.
  The API router iterates over these events and streams them to the browser
  using Server-Sent Events (SSE), giving the user real-time pipeline feedback.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Optional

from src.merger.merge import merge
from src.models.schema import CandidateRecord, LinksData
from src.parsers.csv_parser import ParseError, parse as parse_csv
from src.parsers.resume_parser import parse as parse_resume
from src.projection.projector import project
from src.utils.helpers import get_logger
from src.validator.validator import validate

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pipeline step definitions
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    SKIPPED   = "skipped"


@dataclass
class PipelineStep:
    """Represents one step in the processing pipeline."""
    id:      str
    label:   str
    status:  StepStatus = StepStatus.PENDING
    detail:  str        = ""
    elapsed: float      = 0.0


@dataclass
class PipelineEvent:
    """An event emitted by the pipeline service during processing."""
    type:    str                  # "step_update" | "complete" | "error"
    step:    Optional[PipelineStep] = None
    profile: Optional[dict]       = None
    error:   Optional[str]        = None
    warnings: list[str]           = field(default_factory=list)

    def to_sse(self) -> str:
        """Serialize to Server-Sent Event format."""
        data = {
            "type":     self.type,
            "warnings": self.warnings,
        }
        if self.step:
            data["step"] = {
                "id":      self.step.id,
                "label":   self.step.label,
                "status":  self.step.status.value,
                "detail":  self.step.detail,
                "elapsed": round(self.step.elapsed, 2),
            }
        if self.profile is not None:
            data["profile"] = self.profile
        if self.error:
            data["error"] = self.error
        return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Pipeline steps registry
# ---------------------------------------------------------------------------

def _default_steps() -> list[PipelineStep]:
    return [
        PipelineStep("parse_csv",     "Parsing Recruiter CSV"),
        PipelineStep("parse_resume",  "Parsing Resume PDF"),
        PipelineStep("parse_ats",     "Parsing ATS JSON"),
        PipelineStep("extract",       "Extracting Fields"),
        PipelineStep("normalize",     "Normalising Data"),
        PipelineStep("merge",         "Merging Records"),
        PipelineStep("confidence",    "Assigning Confidence Scores"),
        PipelineStep("validate",      "Validating Schema"),
        PipelineStep("project",       "Applying Output Config"),
    ]


# ---------------------------------------------------------------------------
# Main pipeline service
# ---------------------------------------------------------------------------

class PipelineService:
    """
    Orchestrates the full candidate data transformation pipeline.

    Usage:
        service = PipelineService()
        for event in service.run(csv_bytes, pdf_bytes, ...):
            stream_to_client(event.to_sse())
    """

    def run(
        self,
        csv_bytes:      Optional[bytes] = None,
        pdf_bytes:      Optional[bytes] = None,
        ats_bytes:      Optional[bytes] = None,
        config_text:    str             = "",
        platform_links: dict            = {},
    ) -> Generator[PipelineEvent, None, None]:
        """
        Run the full pipeline, yielding a PipelineEvent after each step.

        CONCEPT — Generator function:
            A function containing `yield` is a generator. When called, it
            returns a generator object. The caller iterates over it — each
            iteration runs the function until the next `yield`, then pauses.
            This is perfect for streaming: we yield an event, send it to
            the client, then continue with the next step.
        """
        steps = _default_steps()
        records: list[CandidateRecord] = []

        def _update(step: PipelineStep, status: StepStatus,
                    detail: str = "", elapsed: float = 0.0) -> PipelineEvent:
            step.status  = status
            step.detail  = detail
            step.elapsed = elapsed
            return PipelineEvent(type="step_update", step=step)

        # Use a temp directory for the duration of this pipeline run
        with tempfile.TemporaryDirectory() as tmp:

            # ── Step 1: Parse CSV ──────────────────────────────────
            step = steps[0]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()

            if csv_bytes:
                csv_path = os.path.join(tmp, "recruiter.csv")
                Path(csv_path).write_bytes(csv_bytes)
                try:
                    csv_record = parse_csv(csv_path)
                    # Inject platform links into CSV record
                    if platform_links:
                        csv_record.links = LinksData(
                            linkedin  = platform_links.get("linkedin")  or csv_record.links.linkedin,
                            github    = platform_links.get("github")    or csv_record.links.github,
                            portfolio = platform_links.get("portfolio") or csv_record.links.portfolio,
                            other     = [v for k, v in platform_links.items()
                                         if k not in ("linkedin","github","portfolio") and v],
                        )
                    records.append(csv_record)
                    elapsed = time.perf_counter() - t0
                    yield _update(step, StepStatus.DONE,
                                  f"Extracted {len(csv_record.skills)} skills, "
                                  f"{len(csv_record.emails)} emails", elapsed)
                except ParseError as e:
                    yield _update(step, StepStatus.FAILED, str(e))
                    yield PipelineEvent(type="error", error=str(e))
                    return
            else:
                yield _update(step, StepStatus.SKIPPED, "No CSV provided")

            # ── Step 2: Parse Resume PDF ───────────────────────────
            step = steps[1]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()

            if pdf_bytes:
                pdf_path = os.path.join(tmp, "resume.pdf")
                Path(pdf_path).write_bytes(pdf_bytes)
                try:
                    # Try AI extraction first, fall back to regex
                    from src.parsers import ai_resume_parser
                    resume_record = None

                    if ai_resume_parser.is_available():
                        yield _update(step, StepStatus.RUNNING, "Using AI extraction...")
                        import pdfplumber
                        with pdfplumber.open(pdf_path) as pdf:
                            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                        resume_record = ai_resume_parser.extract(text)

                    if not resume_record:
                        yield _update(step, StepStatus.RUNNING, "Using regex extraction...")
                        resume_record = parse_resume(pdf_path)

                    records.append(resume_record)
                    elapsed = time.perf_counter() - t0
                    yield _update(step, StepStatus.DONE,
                                  f"Extracted {len(resume_record.skills)} skills, "
                                  f"{len(resume_record.experience)} experience entries",
                                  elapsed)
                except Exception as e:
                    yield _update(step, StepStatus.FAILED, str(e))
                    yield PipelineEvent(type="error", error=f"Resume parsing failed: {e}")
                    return
            else:
                yield _update(step, StepStatus.SKIPPED, "No PDF provided")

            # ── Step 3: Parse ATS JSON ─────────────────────────────
            step = steps[2]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()

            if ats_bytes:
                try:
                    ats_data = json.loads(ats_bytes.decode("utf-8"))
                    ats_record = _parse_ats_json(ats_data)
                    records.append(ats_record)
                    elapsed = time.perf_counter() - t0
                    yield _update(step, StepStatus.DONE,
                                  f"ATS record loaded from {len(ats_data)} fields", elapsed)
                except Exception as e:
                    yield _update(step, StepStatus.SKIPPED, f"ATS parse warning: {e}")
            else:
                yield _update(step, StepStatus.SKIPPED, "No ATS JSON provided")

            # Guard: need at least one record
            if not records:
                err = "At least one input file (CSV or PDF) is required."
                yield PipelineEvent(type="error", error=err)
                return

            # ── Step 4: Field extraction summary ──────────────────
            step = steps[3]
            yield _update(step, StepStatus.RUNNING)
            total_fields = sum(
                len([v for v in [r.full_name, r.headline] if v]) +
                len(r.emails) + len(r.phones) + len(r.skills)
                for r in records
            )
            yield _update(step, StepStatus.DONE,
                          f"{total_fields} field values extracted across {len(records)} source(s)")

            # ── Step 5: Normalisation (happens inside merger) ──────
            step = steps[4]
            yield _update(step, StepStatus.RUNNING)
            yield _update(step, StepStatus.DONE,
                          "Phones → E.164 · Emails → lowercase · Skills → canonical · Dates → ISO 8601")

            # ── Step 6: Merge ──────────────────────────────────────
            step = steps[5]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()
            try:
                profile = merge(records)
                elapsed = time.perf_counter() - t0
                yield _update(step, StepStatus.DONE,
                              f"Merge policy: Resume > CSV · candidate_id={profile.candidate_id[:8]}…",
                              elapsed)
            except Exception as e:
                yield _update(step, StepStatus.FAILED, str(e))
                yield PipelineEvent(type="error", error=f"Merge failed: {e}")
                return

            # ── Step 7: Confidence ─────────────────────────────────
            step = steps[6]
            yield _update(step, StepStatus.RUNNING)
            avg_conf = _avg_confidence(profile)
            yield _update(step, StepStatus.DONE,
                          f"Average field confidence: {avg_conf:.0%}")

            # ── Step 8: Validate ───────────────────────────────────
            step = steps[7]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()
            profile, warnings = validate(profile)
            elapsed = time.perf_counter() - t0
            if warnings:
                yield _update(step, StepStatus.DONE,
                              f"{len(warnings)} warning(s)", elapsed)
            else:
                yield _update(step, StepStatus.DONE, "All checks passed", elapsed)

            # ── Step 9: Project ────────────────────────────────────
            step = steps[8]
            yield _update(step, StepStatus.RUNNING)
            t0 = time.perf_counter()
            config = {}
            if config_text.strip():
                try:
                    config = json.loads(config_text)
                except json.JSONDecodeError:
                    pass
            output = project(profile, config)
            elapsed = time.perf_counter() - t0
            yield _update(step, StepStatus.DONE,
                          f"{len(output)} fields in output", elapsed)

            # ── Complete ───────────────────────────────────────────
            yield PipelineEvent(
                type     = "complete",
                profile  = output,
                warnings = warnings,
            )


# ---------------------------------------------------------------------------
# ATS JSON parser helper
# ---------------------------------------------------------------------------

def _parse_ats_json(data: dict) -> CandidateRecord:
    """Parse a generic ATS JSON payload into a CandidateRecord."""
    from src.models.schema import LocationData, LinksData, ExperienceEntry

    def _s(key: str) -> Optional[str]:
        v = data.get(key)
        return str(v).strip() if v else None

    def _l(key: str) -> list:
        v = data.get(key, [])
        if isinstance(v, str):
            return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
        return [str(x) for x in v if x]

    location = LocationData(
        city    = _s("city"),
        region  = _s("region") or _s("state"),
        country = _s("country"),
    )
    links = LinksData(
        linkedin  = _s("linkedin"),
        github    = _s("github"),
        portfolio = _s("portfolio"),
    )
    experience = [
        ExperienceEntry(
            company    = e.get("company"),
            title      = e.get("title") or e.get("role"),
            start_date = e.get("start_date") or e.get("start"),
            end_date   = e.get("end_date")   or e.get("end"),
        )
        for e in data.get("experience", [])
        if isinstance(e, dict)
    ]
    yrs = data.get("years_experience")
    return CandidateRecord(
        source           = "ATS",
        full_name        = _s("full_name") or _s("name"),
        emails           = _l("emails") or ([data["email"]] if data.get("email") else []),
        phones           = _l("phones") or ([data["phone"]] if data.get("phone") else []),
        location         = location,
        links            = links,
        headline         = _s("headline") or _s("title"),
        years_experience = int(yrs) if yrs else None,
        skills           = _l("skills"),
        experience       = experience,
    )


def _avg_confidence(profile) -> float:
    fields = [
        profile.full_name, profile.emails, profile.phones,
        profile.location, profile.links, profile.headline,
        profile.years_experience, profile.skills,
    ]
    scores = [f.confidence for f in fields if f and f.confidence > 0]
    return sum(scores) / len(scores) if scores else 0.0
