"""
api/main.py
-----------
FastAPI application entry point.

WHY FastAPI over Flask?
  1. Auto-generates /docs (Swagger UI) and /redoc — valuable for internship demos.
  2. Async by design — handles file I/O without blocking.
  3. Pydantic request/response models built-in — same library as our pipeline.
  4. Server-Sent Events (SSE) for real-time pipeline progress streaming.
  5. Industry standard for Python APIs in production.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from api.routers import candidates, pages, auth_router, dashboard

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ProfileForge API",
    description="Multi-Source Candidate Data Transformer — HR-Tech SaaS Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production"),
    max_age=60 * 60 * 24 * 30,   # 30 days
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files & templates
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent.parent

app.mount(
    "/static",
    StaticFiles(directory=str(BASE / "web" / "static")),
    name="static",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(pages.router)           # HTML page routes
app.include_router(candidates.router,      prefix="/api")
app.include_router(auth_router.router,     prefix="/auth")
app.include_router(dashboard.router,       prefix="/api/dashboard")
