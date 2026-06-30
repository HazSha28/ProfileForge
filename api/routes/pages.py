"""
api/routes/pages.py
--------------------
All HTML page routes using Jinja2 templates.

Starlette >= 0.36 changed TemplateResponse signature:
  OLD: TemplateResponse("name.html", {"request": request, ...})
  NEW: TemplateResponse(request, "name.html", {...})

We use the new signature throughout to avoid the
'unhashable type: dict' cache bug in Jinja2.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.responses import RedirectResponse

router = APIRouter(tags=["pages"])

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ctx(request: Request, active_page: str = "", **extra) -> dict:
    """Build the standard template context dict."""
    return {
        "request":     request,
        "user":        request.session.get("user"),
        "active_page": active_page,
        **extra,
    }


# ── Root ──────────────────────────────────────────────────────
@router.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


# ── Dashboard ─────────────────────────────────────────────────
@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, "dashboard")
    )


# ── Single Candidate ──────────────────────────────────────────
@router.get("/candidate")
async def candidate(request: Request):
    return templates.TemplateResponse(
        request, "candidate.html", _ctx(request, "candidate")
    )


# ── Profile result ────────────────────────────────────────────
@router.get("/profile")
async def profile_page(request: Request):
    return templates.TemplateResponse(
        request, "profile.html", _ctx(request, "candidate")
    )


# ── Auth ──────────────────────────────────────────────────────
@router.get("/login")
async def login(request: Request):
    return templates.TemplateResponse(request, "auth.html", {"request": request})


@router.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse(request, "auth.html", {"request": request})


# ── Help ──────────────────────────────────────────────────────
@router.get("/help")
async def help_page(request: Request):
    return templates.TemplateResponse(
        request, "help.html", _ctx(request, "help")
    )


# ── Bulk upload ───────────────────────────────────────────────
@router.get("/bulk")
async def bulk(request: Request):
    return templates.TemplateResponse(
        request, "bulk.html", _ctx(request, "bulk")
    )


@router.get("/bulk/progress")
async def bulk_progress(request: Request):
    return templates.TemplateResponse(
        request, "bulk_progress.html", _ctx(request, "bulk")
    )


@router.get("/bulk/history")
async def bulk_history(request: Request):
    return templates.TemplateResponse(
        request, "bulk_history.html", _ctx(request, "bulk")
    )


# ── History (single-candidate) ────────────────────────────────
@router.get("/history")
async def history(request: Request):
    return templates.TemplateResponse(
        request, "history.html", _ctx(request, "history")
    )


# ── Legal ─────────────────────────────────────────────────────
@router.get("/terms")
async def terms(request: Request):
    return templates.TemplateResponse(request, "terms.html", {"request": request})


@router.get("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {"request": request})
