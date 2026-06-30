"""
api/routes/pages.py
--------------------
All HTML page routes using Jinja2 templates.

FastAPI serves HTML via Jinja2TemplateResponse.
The base.html template provides the full sidebar layout.
Every page extends base.html and fills in the content block.
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


def _user(request: Request) -> dict | None:
    """Extract user from session."""
    return request.session.get("user")


# ---------------------------------------------------------------------------
# Root — redirect to dashboard
# ---------------------------------------------------------------------------

@router.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


# ---------------------------------------------------------------------------
# Dashboard — first page
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":     request,
            "user":        _user(request),
            "active_page": "dashboard",
        },
    )


# ---------------------------------------------------------------------------
# Single Candidate page
# ---------------------------------------------------------------------------

@router.get("/candidate")
async def candidate(request: Request):
    return templates.TemplateResponse(
        "candidate.html",
        {
            "request":     request,
            "user":        _user(request),
            "active_page": "candidate",
        },
    )


# ---------------------------------------------------------------------------
# Profile result page
# ---------------------------------------------------------------------------

@router.get("/profile")
async def profile_page(request: Request):
    return templates.TemplateResponse(
        "profile.html",
        {
            "request":     request,
            "user":        _user(request),
            "active_page": "candidate",
        },
    )


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

@router.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})


@router.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})


# ---------------------------------------------------------------------------
# Info pages
# ---------------------------------------------------------------------------

@router.get("/help")
async def help_page(request: Request):
    return templates.TemplateResponse(
        "help.html",
        {
            "request":     request,
            "user":        _user(request),
            "active_page": "help",
        },
    )


@router.get("/terms")
async def terms(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})


@router.get("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
