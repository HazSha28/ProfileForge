"""
src/bulk/bulk_processor.py
--------------------------
Bulk Candidate Processing orchestration layer.

DESIGN — Orchestration Only
  This module does NOT reimplement any parser, normalizer, merger, or
  validator logic. It reuses PipelineService for each candidate and
  adds only the coordination layer on top:
    - ZIP extraction
    - Multi-row CSV parsing
    - Resume matching
    - Error isolation (one failure never stops others)
    - Summary generation
    - Result persistence to output/bulk_<job_id>/

CONCEPT — Generator pipeline:
  process_bulk() yields BulkEvent objects so the API layer can stream
  real-time progress to the browser via Server-Sent Events (SSE).
  This mirrors the single-candidate PipelineService.run() pattern.

OUTPUT STRUCTURE:
  output/
    bulk_<job_id>/
      candidate_001.json
      candidate_002.json
      ...
      bulk_summary.json
"""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Generator, Iterator, Optional

from src.bulk.bulk_matcher import CsvRow, MatchResult, match_all
from src.services.pipeline import PipelineService, PipelineEvent
from src.utils.helpers import get_logger

logger = get_logger(__name__)

# Output directory (relative to project root)
_OUTPUT_ROOT = Path("output")


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------

class CandidateStatus(str, Enum):
    PENDING         = "pending"
    PROCESSING      = "processing"
    DONE            = "done"
    FAILED          = "failed"
    RESUME_MISSING  = "resume_missing"
    CSV_MISSING     = "csv_missing"


@dataclass
class CandidateResult:
    """Final result for one candidate after the pipeline completes."""
    index:          int
    name:           str
    email:          str
    status:         CandidateStatus
    confidence:     float            = 0.0
    warnings:       list[str]        = field(default_factory=list)
    error:          Optional[str]    = None
    resume_name:    Optional[str]    = None
    match_method:   str              = "none"
    json_path:      Optional[str]    = None
    profile:        Optional[dict]   = None
    processed_at:   str              = ""


@dataclass
class BulkSummary:
    """Aggregated stats for a completed bulk job."""
    job_id:              str
    total_candidates:    int
    processed:           int
    failed:              int
    resume_missing:      int
    csv_missing:         int
    duplicates_removed:  int
    average_confidence:  float
    processing_time:     str
    output_dir:          str
    candidates:          list[CandidateResult]  = field(default_factory=list)


# ---------------------------------------------------------------------------
# Bulk progress events
# ---------------------------------------------------------------------------

@dataclass
class BulkEvent:
    """
    Real-time event yielded by process_bulk() during processing.

    Types:
      "job_start"     — job metadata, total count
      "candidate_start" — about to process candidate N
      "candidate_done"  — candidate N complete (with result)
      "candidate_error" — candidate N failed (processing continues)
      "job_complete"  — all candidates done, summary included
    """
    type:      str
    job_id:    str
    total:     int                       = 0
    current:   int                       = 0
    candidate: Optional[CandidateResult] = None
    summary:   Optional[BulkSummary]     = None
    message:   str                       = ""

    def to_sse(self) -> str:
        """Serialize to Server-Sent Event format."""
        data: dict = {
            "type":    self.type,
            "job_id":  self.job_id,
            "total":   self.total,
            "current": self.current,
            "message": self.message,
        }
        if self.candidate:
            data["candidate"] = {
                "index":        self.candidate.index,
                "name":         self.candidate.name,
                "email":        self.candidate.email,
                "status":       self.candidate.status.value,
                "confidence":   round(self.candidate.confidence, 3),
                "warnings":     self.candidate.warnings,
                "error":        self.candidate.error,
                "resume_name":  self.candidate.resume_name,
                "match_method": self.candidate.match_method,
                "json_path":    self.candidate.json_path,
                "processed_at": self.candidate.processed_at,
                "profile":      self.candidate.profile,   # full profile for View button
            }
        if self.summary:
            data["summary"] = {
                "job_id":              self.summary.job_id,
                "total_candidates":    self.summary.total_candidates,
                "processed":           self.summary.processed,
                "failed":              self.summary.failed,
                "resume_missing":      self.summary.resume_missing,
                "csv_missing":         self.summary.csv_missing,
                "duplicates_removed":  self.summary.duplicates_removed,
                "average_confidence":  round(self.summary.average_confidence, 3),
                "processing_time":     self.summary.processing_time,
                "output_dir":          self.summary.output_dir,
            }
        return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Bulk processor
# ---------------------------------------------------------------------------

class BulkProcessor:
    """
    Orchestrates bulk candidate processing without reimplementing any
    pipeline logic.

    Reuses:
      - src.services.pipeline.PipelineService  (full pipeline per candidate)
      - src.bulk.bulk_matcher.match_all        (resume-to-CSV matching)

    Creates:
      - output/bulk_<job_id>/candidate_NNN.json
      - output/bulk_<job_id>/bulk_summary.json
    """

    def __init__(self) -> None:
        self._pipeline = PipelineService()

    def process_bulk(
        self,
        csv_bytes:  bytes,
        zip_bytes:  bytes,
        config_text: str = "",
    ) -> Generator[BulkEvent, None, None]:
        """
        Process all candidates from a recruiter CSV + resume ZIP.

        Args:
            csv_bytes:   Raw bytes of the recruiter CSV file.
            zip_bytes:   Raw bytes of the ZIP archive containing resumes.
            config_text: Optional JSON config string (projection rules).

        Yields:
            BulkEvent — one event per state change:
              job_start → (candidate_start → candidate_done|candidate_error)* → job_complete
        """
        job_id    = str(uuid.uuid4())[:8]
        job_start = time.perf_counter()

        logger.info("Bulk job %s started.", job_id)

        # --- Step 1: Parse multi-row CSV ---
        try:
            csv_rows = _parse_bulk_csv(csv_bytes)
        except Exception as exc:
            yield BulkEvent(
                type="job_error", job_id=job_id,
                message=f"Failed to parse CSV: {exc}"
            )
            return

        total = len(csv_rows)
        logger.info("Bulk job %s: %d candidate rows parsed.", job_id, total)

        # --- Step 2: Extract resumes from ZIP ---
        try:
            resume_paths, zip_tmpdir = _extract_zip(zip_bytes)
        except Exception as exc:
            yield BulkEvent(
                type="job_error", job_id=job_id,
                message=f"Failed to extract ZIP: {exc}"
            )
            return

        logger.info(
            "Bulk job %s: %d resume files extracted.", job_id, len(resume_paths)
        )

        # --- Step 3: Match resumes to CSV rows ---
        matches, orphans = match_all(csv_rows, resume_paths)

        # Emit job_start so the UI can render the candidate list
        yield BulkEvent(
            type="job_start", job_id=job_id, total=total,
            message=f"{total} candidates · {len(resume_paths)} resumes · {len(orphans)} orphans"
        )

        # --- Step 4: Process each candidate ---
        results: list[CandidateResult] = []
        pipeline_svc = PipelineService()

        for i, match in enumerate(matches, start=1):
            row = match.csv_row
            candidate_name  = row.full_name or f"Candidate {row.index}"
            candidate_email = row.email or ""

            yield BulkEvent(
                type="candidate_start", job_id=job_id,
                total=total, current=i,
                message=f"Processing {candidate_name}",
                candidate=CandidateResult(
                    index=i, name=candidate_name,
                    email=candidate_email,
                    status=CandidateStatus.PROCESSING,
                    resume_name=match.resume_path.name if match.resume_path else None,
                    match_method=match.match_method,
                )
            )

            # Handle resume_missing
            if match.resume_path is None:
                result = CandidateResult(
                    index=i,
                    name=candidate_name,
                    email=candidate_email,
                    status=CandidateStatus.RESUME_MISSING,
                    warnings=match.warnings,
                    match_method="none",
                    processed_at=_now(),
                )
                results.append(result)
                yield BulkEvent(
                    type="candidate_done", job_id=job_id,
                    total=total, current=i,
                    candidate=result,
                )
                continue

            # Run full pipeline for this candidate
            result = self._run_one(
                index=i,
                name=candidate_name,
                email=candidate_email,
                match=match,
                config_text=config_text,
                job_id=job_id,
                pipeline_svc=pipeline_svc,
            )
            results.append(result)

            event_type = "candidate_done" if result.status == CandidateStatus.DONE \
                         else "candidate_error"
            yield BulkEvent(
                type=event_type, job_id=job_id,
                total=total, current=i,
                candidate=result,
            )

        # --- Step 5: Add orphan resumes ---
        for orphan_path in orphans:
            orphan_result = self._run_one_orphan(
                index=len(results) + 1,
                resume_path=orphan_path,
                config_text=config_text,
                pipeline_svc=pipeline_svc,
            )
            results.append(orphan_result)

        # --- Step 6: Save outputs ---
        output_dir = _OUTPUT_ROOT / f"bulk_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        _save_candidate_files(results, output_dir)

        elapsed = time.perf_counter() - job_start
        summary = _build_summary(job_id, results, elapsed, str(output_dir))
        _save_summary(summary, output_dir)

        # --- Cleanup temp zip dir ---
        try:
            import shutil
            shutil.rmtree(zip_tmpdir, ignore_errors=True)
        except Exception:
            pass

        logger.info(
            "Bulk job %s complete: %d/%d processed in %.1fs.",
            job_id, summary.processed, summary.total_candidates, elapsed
        )

        yield BulkEvent(
            type="job_complete", job_id=job_id,
            total=total, current=total,
            summary=summary,
            message=f"Completed in {summary.processing_time}",
        )

    # -----------------------------------------------------------------------
    # Private: run single candidate through PipelineService
    # -----------------------------------------------------------------------

    def _run_one(
        self,
        index:        int,
        name:         str,
        email:        str,
        match:        MatchResult,
        config_text:  str,
        job_id:       str,
        pipeline_svc: PipelineService,
    ) -> CandidateResult:
        """Run the full pipeline for one matched candidate. Never raises."""
        resume_name = match.resume_path.name if match.resume_path else None
        warnings    = list(match.warnings)
        profile     = None

        # Build a single-row CSV bytes for this candidate
        csv_bytes = _row_to_csv_bytes(match.csv_row)

        # Read resume bytes
        try:
            pdf_bytes = match.resume_path.read_bytes()
        except Exception as exc:
            return CandidateResult(
                index=index, name=name, email=email,
                status=CandidateStatus.FAILED,
                error=f"Cannot read resume file: {exc}",
                resume_name=resume_name,
                match_method=match.match_method,
                processed_at=_now(),
            )

        try:
            for event in pipeline_svc.run(
                csv_bytes=csv_bytes,
                pdf_bytes=pdf_bytes,
                config_text=config_text,
            ):
                if event.type == "complete" and event.profile:
                    profile = event.profile
                elif event.type == "error":
                    warnings.append(event.error or "Pipeline error")
                if event.warnings:
                    warnings.extend(event.warnings)

        except Exception as exc:
            logger.error("Bulk job %s — candidate %d failed: %s", job_id, index, exc)
            return CandidateResult(
                index=index, name=name, email=email,
                status=CandidateStatus.FAILED,
                error=str(exc),
                warnings=warnings,
                resume_name=resume_name,
                match_method=match.match_method,
                processed_at=_now(),
            )

        if profile is None:
            return CandidateResult(
                index=index, name=name, email=email,
                status=CandidateStatus.FAILED,
                error="Pipeline produced no output.",
                warnings=warnings,
                resume_name=resume_name,
                match_method=match.match_method,
                processed_at=_now(),
            )

        # Extract resolved name and confidence from profile
        resolved_name = (
            (profile.get("name") or {}).get("value")
            or (profile.get("full_name") or {}).get("value")
            or name
        )
        confidence = _avg_confidence_from_dict(profile)

        return CandidateResult(
            index=index,
            name=str(resolved_name),
            email=email,
            status=CandidateStatus.DONE,
            confidence=confidence,
            warnings=[w for w in warnings if w],
            resume_name=resume_name,
            match_method=match.match_method,
            profile=profile,
            processed_at=_now(),
        )

    def _run_one_orphan(
        self,
        index:        int,
        resume_path:  Path,
        config_text:  str,
        pipeline_svc: PipelineService,
    ) -> CandidateResult:
        """Run pipeline for an orphan resume (no CSV row)."""
        profile  = None
        warnings = [f"No CSV row found for resume '{resume_path.name}'. Status: csv_missing."]

        try:
            pdf_bytes = resume_path.read_bytes()
            for event in pipeline_svc.run(
                pdf_bytes=pdf_bytes,
                config_text=config_text,
            ):
                if event.type == "complete" and event.profile:
                    profile = event.profile
                if event.warnings:
                    warnings.extend(event.warnings)
        except Exception as exc:
            return CandidateResult(
                index=index,
                name=resume_path.stem,
                email="",
                status=CandidateStatus.CSV_MISSING,
                error=str(exc),
                resume_name=resume_path.name,
                match_method="none",
                processed_at=_now(),
            )

        name = "Unknown"
        confidence = 0.0
        if profile:
            name = (
                (profile.get("name") or {}).get("value")
                or (profile.get("full_name") or {}).get("value")
                or resume_path.stem
            )
            confidence = _avg_confidence_from_dict(profile)

        return CandidateResult(
            index=index,
            name=str(name),
            email="",
            status=CandidateStatus.CSV_MISSING,
            confidence=confidence,
            warnings=warnings,
            resume_name=resume_path.name,
            match_method="none",
            profile=profile,
            processed_at=_now(),
        )


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _parse_bulk_csv(csv_bytes: bytes) -> list[CsvRow]:
    """
    Parse all rows from the recruiter CSV.
    Returns list[CsvRow] — one per data row (header excluded).

    Handles flexible column names including:
      - "Name of the Student", "Candidate Name", "full_name", "name"
      - "Registration Number", "Reg No", "Roll No"
      - "Github Profile Url", "LinkedIn Profile Url"
      - "Resume Drive Url", "Resume"
      - "Online Coding Platform URLs"
    """
    _ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    text = None
    for enc in _ENCODINGS:
        try:
            text = csv_bytes.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if text is None:
        raise ValueError("Could not decode CSV bytes with any supported encoding.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file is empty or has no headers.")

    # Normalise headers: strip whitespace + lowercase for lookup
    headers_lower = {h.strip().lower(): h.strip() for h in reader.fieldnames}

    def _col(aliases: list[str]) -> Optional[str]:
        """Return the actual column name for the first matching alias."""
        for alias in aliases:
            alias_lower = alias.strip().lower()
            if alias_lower in headers_lower:
                return headers_lower[alias_lower]
            # Partial / contains match for verbose column names
            for hdr_lower, hdr_orig in headers_lower.items():
                if alias_lower in hdr_lower:
                    return hdr_orig
        return None

    # Name — supports "Name of the Student", "Candidate Name", "full_name", etc.
    col_name = _col([
        "name of the student", "student name", "candidate name",
        "full_name", "fullname", "full name", "name",
    ])

    # Registration / roll number — useful as secondary key
    col_regno = _col([
        "registration number", "reg no", "reg. no", "roll no",
        "roll number", "regno", "registration no",
    ])

    # Email — usually not in a recruiter DB export, but try
    col_email = _col([
        "email", "email address", "email_address", "e-mail", "emails",
    ])

    # Phone — usually not in a recruiter DB export, but try
    col_phone = _col([
        "phone", "phone number", "phone_number", "mobile",
        "telephone", "phones", "contact",
    ])

    # LinkedIn URL
    col_linkedin = _col([
        "linkedin profile url", "linkedin url", "linkedin", "linkedin_url",
    ])

    # GitHub URL
    col_github = _col([
        "github profile url", "github url", "github", "github_url",
    ])

    # Resume link (Drive URL etc.)
    col_resume = _col([
        "resume drive url", "resume url", "resume", "cv url", "cv link",
    ])

    logger.info(
        "CSV columns detected → name=%r regno=%r email=%r phone=%r "
        "linkedin=%r github=%r resume=%r",
        col_name, col_regno, col_email, col_phone,
        col_linkedin, col_github, col_resume,
    )

    rows: list[CsvRow] = []
    for i, row in enumerate(reader, start=1):
        def _get(col: Optional[str]) -> Optional[str]:
            if not col:
                return None
            v = row.get(col, "").strip()
            return v if v else None

        name    = _get(col_name)
        regno   = _get(col_regno)
        email   = _get(col_email)
        phone   = _get(col_phone)
        linkedin = _get(col_linkedin)
        github   = _get(col_github)
        resume_url = _get(col_resume)

        # Augment the raw dict with normalised keys so csv_parser can use it
        augmented_raw = dict(row)
        if name and "full_name" not in augmented_raw:
            augmented_raw["full_name"] = name
        if email and "email" not in augmented_raw:
            augmented_raw["email"] = email
        if phone and "phone" not in augmented_raw:
            augmented_raw["phone"] = phone
        if linkedin and "linkedin" not in augmented_raw:
            augmented_raw["linkedin"] = linkedin

        rows.append(CsvRow(
            index=i,
            full_name=name,
            email=email,
            phone=phone,
            raw=augmented_raw,
            # Extra fields for matching
            regno=regno,
            linkedin=linkedin,
            github=github,
            resume_url=resume_url,
        ))

    logger.info("Parsed %d candidate rows from CSV.", len(rows))
    return rows


def _extract_zip(zip_bytes: bytes) -> tuple[list[Path], str]:
    """
    Extract all PDF/DOCX files from the ZIP archive into a temp directory.

    Returns:
        (list[Path], tmp_dir_str) — the tmp_dir must be cleaned up by caller.
    """
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="pf_bulk_")

    supported = {".pdf", ".docx"}
    resume_paths: list[Path] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            if ext not in supported:
                continue
            # Flatten directory structure: keep only the filename
            dest_name = Path(info.filename).name
            dest_path = Path(tmp_dir) / dest_name
            dest_path.write_bytes(zf.read(info.filename))
            resume_paths.append(dest_path)
            logger.debug("Extracted resume: %s", dest_name)

    return resume_paths, tmp_dir


def _row_to_csv_bytes(row: CsvRow) -> bytes:
    """Serialise a single CsvRow back into minimal CSV bytes for PipelineService."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(row.raw.keys()))
    writer.writeheader()
    writer.writerow(row.raw)
    return buf.getvalue().encode("utf-8")


def _save_candidate_files(results: list[CandidateResult], output_dir: Path) -> None:
    """Write one JSON file per successful candidate."""
    for result in results:
        if result.profile is None:
            continue
        filename = f"candidate_{result.index:03d}.json"
        path = output_dir / filename
        result.json_path = str(path)
        path.write_text(
            json.dumps(result.profile, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.debug("Saved: %s", path)


def _save_summary(summary: BulkSummary, output_dir: Path) -> None:
    """Write bulk_summary.json to the output directory."""
    summary_dict = {
        "job_id":              summary.job_id,
        "total_candidates":    summary.total_candidates,
        "processed":           summary.processed,
        "failed":              summary.failed,
        "resume_missing":      summary.resume_missing,
        "csv_missing":         summary.csv_missing,
        "duplicates_removed":  summary.duplicates_removed,
        "average_confidence":  round(summary.average_confidence, 3),
        "processing_time":     summary.processing_time,
        "output_dir":          summary.output_dir,
        "candidates": [
            {
                "index":       r.index,
                "name":        r.name,
                "email":       r.email,
                "status":      r.status.value,
                "confidence":  round(r.confidence, 3),
                "warnings":    r.warnings,
                "error":       r.error,
                "resume_name": r.resume_name,
                "match_method":r.match_method,
                "json_path":   r.json_path,
                "processed_at":r.processed_at,
            }
            for r in summary.candidates
        ],
    }
    path = output_dir / "bulk_summary.json"
    path.write_text(
        json.dumps(summary_dict, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info("Bulk summary saved: %s", path)


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------

def _build_summary(
    job_id:    str,
    results:   list[CandidateResult],
    elapsed:   float,
    output_dir: str,
) -> BulkSummary:
    processed       = sum(1 for r in results if r.status == CandidateStatus.DONE)
    failed          = sum(1 for r in results if r.status == CandidateStatus.FAILED)
    resume_missing  = sum(1 for r in results if r.status == CandidateStatus.RESUME_MISSING)
    csv_missing     = sum(1 for r in results if r.status == CandidateStatus.CSV_MISSING)

    conf_scores     = [r.confidence for r in results if r.confidence > 0]
    avg_confidence  = sum(conf_scores) / len(conf_scores) if conf_scores else 0.0

    # Duplicates removed: count total warnings that mention "duplicate"
    dup_count = sum(
        sum(1 for w in r.warnings if "duplicate" in w.lower() or "dedup" in w.lower())
        for r in results
    )

    return BulkSummary(
        job_id=job_id,
        total_candidates=len(results),
        processed=processed,
        failed=failed,
        resume_missing=resume_missing,
        csv_missing=csv_missing,
        duplicates_removed=dup_count,
        average_confidence=avg_confidence,
        processing_time=f"{elapsed:.1f} seconds",
        output_dir=output_dir,
        candidates=results,
    )


def _avg_confidence_from_dict(profile: dict) -> float:
    """Extract average confidence score from a projected profile dict."""
    field_keys = [
        "full_name", "name", "emails", "phones",
        "skills", "location", "years_experience", "links",
    ]
    scores = []
    for key in field_keys:
        fv = profile.get(key)
        if isinstance(fv, dict):
            c = fv.get("confidence")
            if isinstance(c, (int, float)) and c > 0:
                scores.append(c)
    return sum(scores) / len(scores) if scores else 0.0


def _now() -> str:
    """Current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
