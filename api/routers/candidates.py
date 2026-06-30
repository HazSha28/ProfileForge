"""
api/routers/candidates.py
--------------------------
WHY THIS FILE EXISTS
--------------------
All candidate processing endpoints live here — single candidate and bulk.
The router handles HTTP mechanics (file uploads, SSE streaming, response codes).
All business logic is delegated to PipelineService.

CONCEPT — FastAPI UploadFile:
    FastAPI automatically handles multipart/form-data file uploads.
    `UploadFile` gives you the filename, content_type, and an async
    read() method. It's much cleaner than Flask's request.files.

CONCEPT — Server-Sent Events (SSE):
    SSE is a browser standard for one-way real-time data streaming from
    server to client over a single HTTP connection. The client uses the
    EventSource API in JavaScript. The server sends text/event-stream
    with each message prefixed by "data: " and ending with "\n\n".
    This is how we show the real-time processing pipeline to the user.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from src.services.pipeline import PipelineService

router = APIRouter(tags=["Candidates"])


# ---------------------------------------------------------------------------
# Single candidate — streaming SSE endpoint
# ---------------------------------------------------------------------------

@router.post("/process/stream")
async def process_candidate_stream(
    csv:            Optional[UploadFile] = File(default=None),
    resume:         Optional[UploadFile] = File(default=None),
    ats:            Optional[UploadFile] = File(default=None),
    config:         Optional[str]        = Form(default=""),
    platform_links: Optional[str]        = Form(default=""),
):
    """
    Process a candidate from uploaded files and stream pipeline progress.

    Returns a Server-Sent Events stream. Each event is a JSON object:
    {
      "type":  "step_update" | "complete" | "error",
      "step":  { "id": ..., "label": ..., "status": ..., "detail": ... },
      "profile": { ... },   // only on "complete"
      "error": "...",        // only on "error"
      "warnings": [...]
    }
    """
    if not csv and not resume:
        raise HTTPException(status_code=400, detail="At least one of CSV or PDF is required.")

    # Read file bytes upfront (UploadFile must be read in async context)
    csv_bytes    = await csv.read()    if csv    else None
    pdf_bytes    = await resume.read() if resume else None
    ats_bytes    = await ats.read()    if ats    else None

    # Parse platform links JSON
    links: dict = {}
    if platform_links:
        try:
            links = json.loads(platform_links)
        except json.JSONDecodeError:
            pass

    async def event_generator():
        """
        CONCEPT — Async generator:
            An async generator uses `yield` inside an `async def` function.
            FastAPI's StreamingResponse iterates over this asynchronously,
            sending each yielded chunk to the client immediately.

            We run the synchronous PipelineService in a thread pool
            (via asyncio.to_thread) so it doesn't block the event loop.
        """
        service = PipelineService()

        # Run the synchronous generator in a thread to not block async loop
        # CONCEPT — asyncio.to_thread:
        #   Runs a sync callable in a separate thread while keeping the
        #   async event loop free to handle other requests.
        loop = asyncio.get_event_loop()

        def run_pipeline():
            events = []
            for event in service.run(
                csv_bytes      = csv_bytes,
                pdf_bytes      = pdf_bytes,
                ats_bytes      = ats_bytes,
                config_text    = config or "",
                platform_links = links,
            ):
                events.append(event.to_sse())
            return events

        events = await asyncio.to_thread(run_pipeline)
        for event_str in events:
            yield event_str
            await asyncio.sleep(0.05)  # Small delay for visual effect

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Single candidate — non-streaming (for programmatic use)
# ---------------------------------------------------------------------------

@router.post("/process")
async def process_candidate(
    csv:            Optional[UploadFile] = File(default=None),
    resume:         Optional[UploadFile] = File(default=None),
    ats:            Optional[UploadFile] = File(default=None),
    config:         Optional[str]        = Form(default=""),
    platform_links: Optional[str]        = Form(default=""),
):
    """
    Process a candidate synchronously and return the complete profile.
    Use this endpoint for programmatic / API-first integrations.
    """
    if not csv and not resume:
        raise HTTPException(status_code=400, detail="At least one of CSV or PDF is required.")

    csv_bytes = await csv.read()    if csv    else None
    pdf_bytes = await resume.read() if resume else None
    ats_bytes = await ats.read()    if ats    else None

    links: dict = {}
    if platform_links:
        try:
            links = json.loads(platform_links)
        except json.JSONDecodeError:
            pass

    service = PipelineService()
    profile = None
    warnings = []
    error = None

    for event in service.run(
        csv_bytes      = csv_bytes,
        pdf_bytes      = pdf_bytes,
        ats_bytes      = ats_bytes,
        config_text    = config or "",
        platform_links = links,
    ):
        if event.type == "complete":
            profile  = event.profile
            warnings = event.warnings
        elif event.type == "error":
            error = event.error

    if error:
        raise HTTPException(status_code=422, detail=error)

    return {
        "success":  True,
        "profile":  profile,
        "warnings": warnings,
    }
