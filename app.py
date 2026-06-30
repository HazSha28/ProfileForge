"""
app.py — ProfileForge Flask Server
------------------------------------
Flask web application — dashboard-first layout.

Routes:
  GET  /                   → redirect to /dashboard
  GET  /dashboard          → Dashboard (landing page)
  GET  /candidate          → Single candidate upload page
  GET  /profile            → Profile result page
  POST /api/process        → Pipeline API (JSON response)
  POST /api/process/stream → Server-Sent Events pipeline stream
  GET  /api/health         → Health check
  GET  /login  /signup     → Auth page
  GET  /help               → Help & docs
  GET  /terms  /privacy    → Legal pages
  GET  /auth/google        → Google OAuth
  GET  /auth/github        → GitHub OAuth
  GET  /logout             → Clear session
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, Response, jsonify, redirect, render_template,
    request, session, stream_with_context, url_for,
)

from src.merger.merge import merge
from src.models.schema import LinksData
from src.parsers.csv_parser import ParseError, parse as parse_csv
from src.parsers.resume_parser import parse as parse_resume
from src.projection.projector import project
from src.utils.helpers import get_logger
from src.validator.validator import validate
from auth_oauth import init_oauth, oauth_bp

logger = get_logger("profileforge.web")

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="web/static", template_folder="web/templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 16 MB

app.register_blueprint(oauth_bp)
init_oauth(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _user():
    return session.get("user")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def root():
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", user=_user(), active_page="dashboard")


@app.route("/candidate")
def candidate():
    return render_template("candidate.html", user=_user(), active_page="candidate")


@app.route("/profile")
def profile_page():
    return render_template("profile.html", user=_user(), active_page="candidate")


@app.route("/login")
def login():
    return render_template("auth.html")


@app.route("/signup")
def signup():
    return render_template("auth.html")


@app.route("/help")
def help_page():
    return render_template("help.html", user=_user(), active_page="help")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/history")
def history():
    return render_template("history.html", user=_user(), active_page="history")


@app.route("/processing")
def processing():
    # Legacy redirect — pipeline now runs inline on /candidate
    return redirect("/candidate")


# ---------------------------------------------------------------------------
# API — health
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "ProfileForge", "version": "2.0.0"})


# ---------------------------------------------------------------------------
# API — pipeline (JSON response)
# ---------------------------------------------------------------------------

@app.route("/api/process", methods=["POST"])
def process():
    if "csv" not in request.files or "resume" not in request.files:
        return jsonify({"error": "Both 'csv' and 'resume' files are required."}), 400

    csv_file  = request.files["csv"]
    pdf_file  = request.files["resume"]

    if not csv_file.filename or not pdf_file.filename:
        return jsonify({"error": "No file selected."}), 400

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = os.path.join(tmp, "recruiter.csv")
        pdf_path = os.path.join(tmp, "resume.pdf")
        csv_file.save(csv_path)
        pdf_file.save(pdf_path)

        cfg = _parse_json_field("config")
        links_dict = _parse_json_field("platform_links")

        try:
            csv_record = parse_csv(csv_path)
        except ParseError as e:
            return jsonify({"error": f"CSV parsing failed: {e}"}), 422

        _inject_links(csv_record, links_dict)

        try:
            resume_record = parse_resume(pdf_path)
        except ParseError as e:
            return jsonify({"error": f"Resume parsing failed: {e}"}), 422

        try:
            profile = merge([csv_record, resume_record])
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify({"error": f"Merge failed: {e}"}), 500

        profile, warnings = validate(profile)
        output = project(profile, cfg)

        return jsonify({"success": True, "profile": output, "warnings": warnings})


# ---------------------------------------------------------------------------
# API — pipeline SSE stream
# ---------------------------------------------------------------------------

@app.route("/api/process/stream", methods=["POST"])
def process_stream():
    """
    Server-Sent Events endpoint.
    Streams each pipeline stage to the browser so the UI can show
    a live progress screen.

    SSE format:
      event: stage
      data: {"step": "CSV Parsed", "status": "done"}

      event: complete
      data: {"profile": {...}, "warnings": [...]}

      event: error
      data: {"message": "..."}
    """
    # Read files BEFORE entering the generator
    # (Flask request context doesn't survive into the generator)
    csv_bytes  = request.files["csv"].read()  if "csv"    in request.files else b""
    pdf_bytes  = request.files["resume"].read() if "resume" in request.files else b""
    cfg        = _parse_json_field("config")
    links_dict = _parse_json_field("platform_links")

    def generate():
        import time

        def sse(event, data):
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "recruiter.csv")
            pdf_path = os.path.join(tmp, "resume.pdf")

            with open(csv_path, "wb") as f: f.write(csv_bytes)
            with open(pdf_path, "wb") as f: f.write(pdf_bytes)

            # Stage 1 — CSV
            yield sse("stage", {"step": "Parsing CSV", "status": "running"})
            try:
                csv_record = parse_csv(csv_path)
                _inject_links(csv_record, links_dict)
                yield sse("stage", {"step": "CSV Parsed", "status": "done"})
            except ParseError as e:
                yield sse("error", {"message": str(e)})
                return

            # Stage 2 — PDF
            yield sse("stage", {"step": "Parsing Resume PDF", "status": "running"})
            try:
                resume_record = parse_resume(pdf_path)
                yield sse("stage", {"step": "Resume Parsed", "status": "done"})
            except ParseError as e:
                yield sse("error", {"message": str(e)})
                return

            # Stage 3 — Normalise (happens inside merge)
            yield sse("stage", {"step": "Extracting Fields", "status": "done"})
            yield sse("stage", {"step": "Normalising Data", "status": "running"})

            # Stage 4 — Merge
            try:
                profile = merge([csv_record, resume_record])
                yield sse("stage", {"step": "Emails Normalised",         "status": "done"})
                yield sse("stage", {"step": "Phones Converted to E.164", "status": "done"})
                yield sse("stage", {"step": "Skills Canonicalised",      "status": "done"})
                yield sse("stage", {"step": "Merge Completed",           "status": "done"})
                yield sse("stage", {"step": "Confidence Assigned",       "status": "done"})
            except Exception as e:
                yield sse("error", {"message": f"Merge failed: {e}"})
                return

            # Stage 5 — Validate
            try:
                profile, warnings = validate(profile)
                yield sse("stage", {"step": "Validation Passed", "status": "done"})
            except Exception as e:
                yield sse("error", {"message": f"Validation failed: {e}"})
                return

            # Stage 6 — Project
            try:
                output = project(profile, cfg)
                yield sse("stage", {"step": "Profile Generated", "status": "done"})
            except Exception as e:
                yield sse("error", {"message": f"Projection failed: {e}"})
                return

            yield sse("complete", {"profile": output, "warnings": warnings})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(field_name: str) -> dict:
    raw = request.form.get(field_name, "")
    if raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {}


def _inject_links(csv_record, links_dict: dict):
    if not links_dict:
        return
    csv_record.links = LinksData(
        linkedin  = links_dict.get("linkedin")  or csv_record.links.linkedin,
        github    = links_dict.get("github")    or csv_record.links.github,
        portfolio = links_dict.get("portfolio") or csv_record.links.portfolio,
        other=[v for k, v in links_dict.items()
               if k not in ("linkedin", "github", "portfolio") and v],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  ProfileForge — Flask Server")
    print("  Open: http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)
