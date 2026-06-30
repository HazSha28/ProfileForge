"""
api/routes/bulk.py
------------------
FastAPI routes for Bulk Candidate Processing.

Endpoints:
  POST /api/bulk/process/stream  — SSE stream, real-time progress
  POST /api/bulk/process         — Sync JSON response (for testing)
  GET  /api/bulk/jobs/{job_id}   — Retrieve a completed job summary

Follows the same pattern as api/routes/pipeline.py.
Does NOT duplicate any pipeline logic — delegates entirely to BulkProcessor.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from src.bulk.bulk_processor import BulkProcessor
from src.utils.helpers import get_logger

logger = get_logger("profileforge.bulk_api")

router = APIRouter(prefix="/api/bulk", tags=["bulk"])

# One shared processor instance (stateless — safe to share)
_processor = BulkProcessor()


# ---------------------------------------------------------------------------
# SSE streaming endpoint  — primary endpoint used by the UI
# ---------------------------------------------------------------------------

@router.post("/process/stream")
async def bulk_process_stream(
    csv:    UploadFile          = File(..., description="Recruiter CSV"),
    zip:    UploadFile          = File(..., description="Resume ZIP archive"),
    config: Optional[str]       = Form(None, description="Optional JSON projection config"),
):
    """
    Start a bulk processing job and stream live progress via Server-Sent Events.

    Each SSE message is a JSON object with `type` field:
      job_start        → {job_id, total, message}
      candidate_start  → {current, candidate: {name, email, ...}}
      candidate_done   → {current, candidate: {status, confidence, ...}}
      candidate_error  → {current, candidate: {error, ...}}
      job_complete     → {summary: {...}}
      job_error        → {message: "..."}
    """
    csv_bytes = await csv.read()
    zip_bytes = await zip.read()
    config_text = config or ""

    async def event_stream():
        # Run the synchronous bulk processor in a thread pool so we don't
        # block the async event loop (pdfplumber and Gemini are sync).
        loop = asyncio.get_event_loop()

        # Collect all events from the sync generator in a thread
        def _collect():
            return list(_processor.process_bulk(
                csv_bytes=csv_bytes,
                zip_bytes=zip_bytes,
                config_text=config_text,
            ))

        events = await loop.run_in_executor(None, _collect)

        for event in events:
            yield event.to_sse()
            await asyncio.sleep(0)   # yield control to event loop between events

        yield "data: {\"type\": \"stream_end\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Synchronous JSON endpoint  — useful for testing / non-SSE clients
# ---------------------------------------------------------------------------

@router.post("/process")
async def bulk_process(
    csv:    UploadFile          = File(...),
    zip:    UploadFile          = File(...),
    config: Optional[str]       = Form(None),
):
    """
    Run bulk processing and return the complete summary as JSON.
    Blocks until all candidates are processed.
    """
    csv_bytes   = await csv.read()
    zip_bytes   = await zip.read()
    config_text = config or ""

    loop   = asyncio.get_event_loop()
    events = await loop.run_in_executor(
        None,
        lambda: list(_processor.process_bulk(
            csv_bytes=csv_bytes,
            zip_bytes=zip_bytes,
            config_text=config_text,
        ))
    )

    # Find the final job_complete event
    complete_event = next(
        (e for e in reversed(events) if e.type == "job_complete"), None
    )
    if not complete_event or not complete_event.summary:
        # Check for job_error
        error_event = next(
            (e for e in events if e.type == "job_error"), None
        )
        error_msg = error_event.message if error_event else "Bulk processing failed."
        raise HTTPException(status_code=500, detail=error_msg)

    s = complete_event.summary
    return JSONResponse(content={
        "success": True,
        "job_id":              s.job_id,
        "total_candidates":    s.total_candidates,
        "processed":           s.processed,
        "failed":              s.failed,
        "resume_missing":      s.resume_missing,
        "csv_missing":         s.csv_missing,
        "duplicates_removed":  s.duplicates_removed,
        "average_confidence":  round(s.average_confidence, 3),
        "processing_time":     s.processing_time,
        "output_dir":          s.output_dir,
    })
