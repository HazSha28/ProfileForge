"""
api/routes/pipeline.py
-----------------------
FastAPI API routes for the transformation pipeline.

Key FastAPI concepts used here:
  - UploadFile: FastAPI's async file upload type (replaces Flask's request.files)
  - Form: reads form fields from multipart/form-data
  - JSONResponse: returns structured JSON
  - HTTPException: raises HTTP errors with status codes
"""

from __future__ import annotations

import json
import tempfile
import traceback
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src.merger.merge import merge
from src.models.schema import LinksData
from src.parsers.csv_parser import ParseError, parse as parse_csv
from src.parsers.resume_parser import parse as parse_resume
from src.projection.projector import project
from src.utils.helpers import get_logger
from src.validator.validator import validate

logger = get_logger("profileforge.api")

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "ProfileForge", "version": "1.0.0"}


@router.post("/process")
async def process(
    csv: UploadFile = File(..., description="Recruiter CSV file"),
    resume: UploadFile = File(..., description="Resume PDF file"),
    config: Optional[str] = Form(None, description="JSON config string"),
    platform_links: Optional[str] = Form(None, description="JSON object of platform URLs"),
):
    """
    Run the full ProfileForge pipeline.

    Accepts a multipart form with:
      - csv: recruiter CSV file
      - resume: resume PDF file
      - config: optional JSON config string
      - platform_links: optional JSON object of platform URLs

    Returns the canonical candidate profile with provenance and confidence scores.
    """
    # --- Write uploads to temp files ---
    # FastAPI UploadFile gives us async file-like objects.
    # We read their bytes and write to temp files for our parsers.
    with tempfile.TemporaryDirectory() as tmp_dir:
        import os
        from pathlib import Path

        csv_path = os.path.join(tmp_dir, "recruiter.csv")

        # Preserve the actual file extension so resume_parser knows PDF vs DOCX
        resume_ext = Path(resume.filename or "resume.pdf").suffix.lower() or ".pdf"
        if resume_ext not in (".pdf", ".docx"):
            resume_ext = ".pdf"
        resume_path = os.path.join(tmp_dir, f"resume{resume_ext}")

        csv_bytes = await csv.read()
        with open(csv_path, "wb") as f:
            f.write(csv_bytes)

        pdf_bytes = await resume.read()
        with open(resume_path, "wb") as f:
            f.write(pdf_bytes)

        # --- Parse config ---
        cfg: dict = {}
        if config and config.strip():
            try:
                cfg = json.loads(config)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid config JSON: {exc}")

        # --- Parse platform links ---
        links_dict: dict = {}
        if platform_links and platform_links.strip():
            try:
                links_dict = json.loads(platform_links)
            except json.JSONDecodeError:
                pass

        # --- Stage 1: Parse ---
        try:
            csv_record = parse_csv(csv_path)
        except ParseError as exc:
            logger.error("CSV parse failed: %s", exc)
            raise HTTPException(status_code=422, detail=f"CSV parsing failed: {exc}")

        if links_dict:
            csv_record.links = LinksData(
                linkedin  = links_dict.get("linkedin")  or csv_record.links.linkedin,
                github    = links_dict.get("github")    or csv_record.links.github,
                portfolio = links_dict.get("portfolio") or csv_record.links.portfolio,
                other=[u for k, u in links_dict.items()
                       if k not in ("linkedin", "github", "portfolio") and u],
            )

        try:
            resume_record = parse_resume(resume_path)
        except ParseError as exc:
            logger.error("Resume parse failed: %s", exc)
            raise HTTPException(status_code=422, detail=f"Resume parsing failed: {exc}")

        # --- Stage 2: Merge ---
        try:
            profile = merge([csv_record, resume_record])
        except Exception as exc:
            logger.error("Merge failed: %s", traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Merge failed: {exc}")

        # --- Stage 3: Validate ---
        try:
            profile, warnings = validate(profile)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Validation failed: {exc}")

        # --- Stage 4: Project ---
        try:
            output = project(profile, cfg)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Projection failed: {exc}")

        logger.info(
            "Pipeline complete — candidate: %s",
            output.get("name") or (output.get("full_name") or {}).get("value", "unknown"),
        )

        return JSONResponse(content={"success": True, "profile": output, "warnings": warnings})


@router.post("/process/stream")
async def process_stream(
    csv: UploadFile = File(...),
    resume: UploadFile = File(...),
    config: Optional[str] = Form(None),
    platform_links: Optional[str] = Form(None),
):
    """
    Server-Sent Events version of /process.
    Streams pipeline stage updates to the browser in real time.
    Each stage emits a JSON event so the UI can show a live progress screen.
    """
    import asyncio
    from fastapi.responses import StreamingResponse

    csv_bytes = await csv.read()
    pdf_bytes = await resume.read()

    async def event_stream():
        import os, json, tempfile

        # Stage: Parse
        yield _sse("progress", {"stage": "parse", "status": "running", "progress": 10})
        await asyncio.sleep(0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "recruiter.csv")
            pdf_path = os.path.join(tmp_dir, "resume.pdf")
            with open(csv_path, "wb") as f: f.write(csv_bytes)
            with open(pdf_path, "wb") as f: f.write(pdf_bytes)

            cfg = {}
            if config and config.strip():
                try: cfg = json.loads(config)
                except: pass

            links_dict = {}
            if platform_links and platform_links.strip():
                try: links_dict = json.loads(platform_links)
                except: pass

            try:
                csv_record = parse_csv(csv_path)
                yield _sse("progress", {"stage": "parse", "status": "done", "progress": 20})
            except ParseError as exc:
                yield _sse("error", {"message": str(exc)})
                return

            if links_dict:
                csv_record.links = LinksData(
                    linkedin  = links_dict.get("linkedin")  or csv_record.links.linkedin,
                    github    = links_dict.get("github")    or csv_record.links.github,
                    portfolio = links_dict.get("portfolio") or csv_record.links.portfolio,
                    other=[u for k, u in links_dict.items()
                           if k not in ("linkedin", "github", "portfolio") and u],
                )

            try:
                resume_record = parse_resume(pdf_path)
                yield _sse("progress", {"stage": "parse", "status": "done", "progress": 30})
            except ParseError as exc:
                yield _sse("error", {"message": str(exc)})
                return

            # Stage: Normalize
            yield _sse("progress", {"stage": "normalize", "status": "running", "progress": 40})
            await asyncio.sleep(0)

            try:
                profile = merge([csv_record, resume_record])
                yield _sse("progress", {"stage": "normalize", "status": "done", "progress": 50})
            except Exception as exc:
                yield _sse("error", {"message": f"Merge failed: {exc}"})
                return

            # Stage: Merge
            yield _sse("progress", {"stage": "merge", "status": "done", "progress": 60})
            await asyncio.sleep(0)

            # Stage: Confidence
            yield _sse("progress", {"stage": "confidence", "status": "done", "progress": 70})
            await asyncio.sleep(0)

            # Stage: Validate
            yield _sse("progress", {"stage": "validate", "status": "running", "progress": 80})
            await asyncio.sleep(0)

            try:
                profile, warnings = validate(profile)
                yield _sse("progress", {"stage": "validate", "status": "done", "progress": 90})
            except Exception as exc:
                yield _sse("error", {"message": f"Validation failed: {exc}"})
                return

            # Stage: Project
            yield _sse("progress", {"stage": "project", "status": "running", "progress": 95})
            await asyncio.sleep(0)

            try:
                output = project(profile, cfg)
                yield _sse("progress", {"stage": "project", "status": "done", "progress": 100})
            except Exception as exc:
                yield _sse("error", {"message": f"Projection failed: {exc}"})
                return

            yield _sse("complete", {"profile": output, "warnings": warnings})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    import json
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
