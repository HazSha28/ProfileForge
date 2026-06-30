"""
app.py — ProfileForge Web Server
---------------------------------
Flask web application that exposes the ProfileForge pipeline as a web API.

Routes:
  GET  /              → Serve the frontend HTML page
  POST /api/process   → Accept CSV + PDF uploads, run pipeline, return JSON
  GET  /api/health    → Health check endpoint
  GET  /auth/google   → Start Google OAuth flow
  GET  /auth/github   → Start GitHub OAuth flow
  GET  /logout        → Clear session and redirect to login
"""

from __future__ import annotations

import json
import os
import tempfile
import traceback
from pathlib import Path

# Load .env file before anything else
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, render_template, request, send_from_directory, session

from src.merger.merge import merge
from src.parsers.csv_parser import ParseError, parse as parse_csv
from src.parsers.resume_parser import parse as parse_resume
from src.projection.projector import load_config, project
from src.utils.helpers import get_logger
from src.validator.validator import validate
from auth_oauth import oauth_bp, init_oauth

logger = get_logger("profileforge.web")

app = Flask(__name__, static_folder="web/static", template_folder="web/templates")

# Secret key for session encryption
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

# Register OAuth blueprint and providers
app.register_blueprint(oauth_bp)
init_oauth(app)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main web UI."""
    user = session.get("user")
    return render_template("index.html", user=user)


@app.route("/login")
def login():
    """Serve the auth page."""
    return render_template("auth.html")


@app.route("/signup")
def signup():
    """Serve the auth page with sign-up tab active."""
    return render_template("auth.html")


@app.route("/help")
def help_page():
    """Serve the help & documentation page."""
    return render_template("help.html")


@app.route("/terms")
def terms():
    """Serve the Terms and Conditions page."""
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    """Serve the Privacy Policy page."""
    return render_template("privacy.html")


@app.route("/api/health")
def health():
    """Simple health check."""
    return jsonify({"status": "ok", "service": "ProfileForge"})


@app.route("/api/process", methods=["POST"])
def process():
    """
    Accept a CSV file and a PDF resume, run the full pipeline, return JSON.

    Expected form fields:
      csv    — the recruiter CSV file
      resume — the resume PDF file
      config — optional JSON config text (inline, not a file)
    """
    # --- Validate uploads ---
    if "csv" not in request.files or "resume" not in request.files:
        return jsonify({"error": "Both 'csv' and 'resume' files are required."}), 400

    csv_file = request.files["csv"]
    resume_file = request.files["resume"]

    if csv_file.filename == "" or resume_file.filename == "":
        return jsonify({"error": "No file selected for one or both inputs."}), 400

    # --- Write uploads to a temporary directory ---
    # We use tempfile so we never pollute the project folder with user uploads.
    with tempfile.TemporaryDirectory() as tmp_dir:
        csv_path = os.path.join(tmp_dir, "recruiter.csv")
        pdf_path = os.path.join(tmp_dir, "resume.pdf")

        csv_file.save(csv_path)
        resume_file.save(pdf_path)

        # --- Optional config ---
        config_text = request.form.get("config", "")
        config: dict = {}
        if config_text.strip():
            try:
                config = json.loads(config_text)
            except json.JSONDecodeError as exc:
                return jsonify({"error": f"Invalid config JSON: {exc}"}), 400

        # --- Optional platform links from recruiter ---
        platform_links_text = request.form.get("platform_links", "")
        platform_links: dict = {}
        if platform_links_text.strip():
            try:
                platform_links = json.loads(platform_links_text)
            except json.JSONDecodeError:
                pass  # ignore malformed links silently

        # --- Run the pipeline ---
        try:
            csv_record = parse_csv(csv_path)
        except ParseError as exc:
            logger.error("CSV parse failed: %s", exc)
            return jsonify({"error": f"CSV parsing failed: {exc}"}), 422

        # Inject any recruiter-supplied platform links into the CSV record
        if platform_links:
            from src.models.schema import LinksData
            csv_record.links = LinksData(
                linkedin   = platform_links.get("linkedin")   or csv_record.links.linkedin,
                github     = platform_links.get("github")     or csv_record.links.github,
                portfolio  = platform_links.get("portfolio")  or csv_record.links.portfolio,
                other=[u for k, u in platform_links.items()
                       if k not in ("linkedin", "github", "portfolio") and u],
            )
            logger.info("Injected %d platform link(s) from recruiter form", len(platform_links))

        try:
            resume_record = parse_resume(pdf_path)
        except ParseError as exc:
            logger.error("Resume parse failed: %s", exc)
            return jsonify({"error": f"Resume parsing failed: {exc}"}), 422

        try:
            profile = merge([csv_record, resume_record])
        except Exception as exc:
            logger.error("Merge failed: %s", traceback.format_exc())
            return jsonify({"error": f"Merge failed: {exc}"}), 500

        try:
            profile, warnings = validate(profile)
        except Exception as exc:
            logger.error("Validation failed: %s", exc)
            return jsonify({"error": f"Validation failed: {exc}"}), 500

        try:
            output = project(profile, config)
        except Exception as exc:
            logger.error("Projection failed: %s", exc)
            return jsonify({"error": f"Projection failed: {exc}"}), 500

        logger.info("Pipeline completed for candidate: %s", output.get("name") or output.get("full_name", {}).get("value"))

        return jsonify({
            "success": True,
            "profile": output,
            "warnings": warnings,
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  ProfileForge Web UI")
    print("  Open: http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)
