"""
server.py — ProfileForge FastAPI Server
----------------------------------------
Replaces Flask app.py with FastAPI.

Why FastAPI over Flask:
  - Async by default (handles file uploads without blocking)
  - Native Pydantic validation (we already use Pydantic everywhere)
  - Built-in /docs (Swagger UI) for free at http://127.0.0.1:8000/docs
  - Type hints enforced — matches the rest of the codebase
  - Production-grade with Uvicorn ASGI server

Architecture:
  server.py             — app factory, mounts routers
  api/routes/pages.py   — HTML page routes (Jinja2 templates)
  api/routes/pipeline.py— API routes (JSON endpoints)
  api/routes/oauth.py   — OAuth routes (Google + GitHub)
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from api.routes import pages, pipeline, oauth

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ProfileForge",
    description="Multi-Source Candidate Data Transformer",
    version="1.0.0",
    docs_url="/docs",        # Swagger UI — free with FastAPI
    redoc_url="/redoc",
)

# Session middleware — needed for OAuth state + user session
# Uses itsdangerous signed cookies under the hood
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production"),
    session_cookie="pf_session",
    max_age=60 * 60 * 24 * 30,   # 30 days
    https_only=False,              # set True in production
)

# Static files — serve /static/* from web/static/
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)

# Register all routers
app.include_router(oauth.router)       # /auth/google, /auth/github, /logout
app.include_router(pipeline.router)    # /api/process, /api/health
app.include_router(pages.router)       # /, /dashboard, /candidate, /login, etc.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("\n  ProfileForge — FastAPI Server")
    print("  App:  http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
