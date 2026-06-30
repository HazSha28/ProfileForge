"""
api/routers/pages.py
---------------------
HTML page routes — serves all Jinja2 templates.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Pages"])

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent.parent.parent / "web" / "templates")
)


def _ctx(request: Request, **kwargs) -> dict:
    """Build template context with common variables."""
    return {"request": request, "user": request.session.get("user"), **kwargs}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return TEMPLATES.TemplateResponse("home.html", _ctx(request))


@router.get("/candidate", response_class=HTMLResponse)
async def candidate_page(request: Request):
    return TEMPLATES.TemplateResponse("candidate.html", _ctx(request))


@router.get("/processing", response_class=HTMLResponse)
async def processing_page(request: Request):
    return TEMPLATES.TemplateResponse("processing.html", _ctx(request))


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    return TEMPLATES.TemplateResponse("profile.html", _ctx(request))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return TEMPLATES.TemplateResponse("dashboard.html", _ctx(request))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return TEMPLATES.TemplateResponse("auth.html", _ctx(request))


@router.get("/help", response_class=HTMLResponse)
async def help_page(request: Request):
    return TEMPLATES.TemplateResponse("help.html", _ctx(request))


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    return TEMPLATES.TemplateResponse("terms.html", _ctx(request))


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return TEMPLATES.TemplateResponse("privacy.html", _ctx(request))
