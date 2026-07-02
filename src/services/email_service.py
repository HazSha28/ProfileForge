"""
src/services/email_service.py
------------------------------
Email notification service for ProfileForge.

Sends a summary email when a bulk job completes.
Uses Python's built-in smtplib — no extra packages needed.

Configuration (add to .env):
  EMAIL_HOST      SMTP server (e.g. smtp.gmail.com)
  EMAIL_PORT      SMTP port (587 for TLS, 465 for SSL)
  EMAIL_USER      Sender email address
  EMAIL_PASSWORD  App password (for Gmail: Settings → Security → App Passwords)
  EMAIL_FROM_NAME Display name for sender (default: ProfileForge)

Gmail setup:
  1. Enable 2FA on your Google account
  2. Go to myaccount.google.com → Security → App Passwords
  3. Generate a password for "Mail" → use that as EMAIL_PASSWORD
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from src.utils.helpers import get_logger

logger = get_logger(__name__)


def is_configured() -> bool:
    """Return True if all required email env vars are set."""
    return all([
        os.environ.get("EMAIL_HOST"),
        os.environ.get("EMAIL_USER"),
        os.environ.get("EMAIL_PASSWORD"),
    ])


def send_bulk_summary(
    to_email:    str,
    job_id:      str,
    total:       int,
    processed:   int,
    failed:      int,
    missing:     int,
    avg_conf:    float,
    duration:    str,
    output_dir:  str,
) -> bool:
    """
    Send a bulk job completion summary email.

    Args:
        to_email:   Recipient email address (usually the logged-in user).
        job_id:     Bulk job identifier.
        total:      Total candidates in the job.
        processed:  Successfully processed count.
        failed:     Failed count.
        missing:    Resume-missing count.
        avg_conf:   Average confidence score (0.0–1.0).
        duration:   Processing time string (e.g. "15.2 seconds").
        output_dir: Path to output directory.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not is_configured():
        logger.info("Email not configured — skipping bulk summary notification.")
        return False

    if not to_email:
        logger.warning("No recipient email — skipping notification.")
        return False

    host     = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    port     = int(os.environ.get("EMAIL_PORT", "587"))
    user     = os.environ.get("EMAIL_USER", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    from_name = os.environ.get("EMAIL_FROM_NAME", "ProfileForge")

    subject  = f"✅ Bulk Job {job_id} Complete — {processed}/{total} candidates processed"
    html     = _build_html(job_id, total, processed, failed, missing, avg_conf, duration)
    text     = _build_text(job_id, total, processed, failed, missing, avg_conf, duration)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{user}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(user, to_email, msg.as_string())
        logger.info("Bulk summary email sent to %s (job %s)", to_email, job_id)
        return True

    except Exception as exc:
        logger.error("Failed to send bulk summary email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def _build_html(
    job_id: str, total: int, processed: int, failed: int,
    missing: int, avg_conf: float, duration: str,
) -> str:
    conf_pct  = round(avg_conf * 100)
    conf_color = "#3a7d52" if conf_pct >= 80 else "#b07d20" if conf_pct >= 60 else "#963030"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f0eeeb;font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="max-width:560px;margin:40px auto;background:#faf8f5;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(107,63,31,.12);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0d1b2a,#162032);padding:28px 32px;">
      <div style="font-size:1.3rem;font-weight:800;color:#f0eeeb;margin-bottom:4px;">ProfileForge</div>
      <div style="font-size:.9rem;color:#7a8fa8;">Bulk Processing Complete</div>
    </div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <h2 style="font-size:1.1rem;font-weight:700;color:#3b2010;margin-bottom:6px;">Job {job_id}</h2>
      <p style="font-size:.875rem;color:#7a5540;margin-bottom:24px;">
        Completed in {duration}. Here's your summary:
      </p>

      <!-- Stats grid -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px;">
        <div style="background:#f0eeeb;border-radius:10px;padding:16px;text-align:center;">
          <div style="font-size:1.8rem;font-weight:800;color:#3a7d52">{processed}</div>
          <div style="font-size:.75rem;color:#a0816a;margin-top:4px">Processed</div>
        </div>
        <div style="background:#f0eeeb;border-radius:10px;padding:16px;text-align:center;">
          <div style="font-size:1.8rem;font-weight:800;color:{conf_color}">{conf_pct}%</div>
          <div style="font-size:.75rem;color:#a0816a;margin-top:4px">Avg Confidence</div>
        </div>
        <div style="background:#f0eeeb;border-radius:10px;padding:16px;text-align:center;">
          <div style="font-size:1.8rem;font-weight:800;color:#b07d20">{missing}</div>
          <div style="font-size:.75rem;color:#a0816a;margin-top:4px">Resume Missing</div>
        </div>
        <div style="background:#f0eeeb;border-radius:10px;padding:16px;text-align:center;">
          <div style="font-size:1.8rem;font-weight:800;color:#963030">{failed}</div>
          <div style="font-size:.75rem;color:#a0816a;margin-top:4px">Failed</div>
        </div>
      </div>

      <p style="font-size:.82rem;color:#a0816a;margin-bottom:20px;">
        Total candidates: <strong style="color:#3b2010">{total}</strong>
      </p>

      <!-- CTA -->
      <a href="#" style="display:inline-block;background:#6b3f1f;color:#f2e8d9;padding:11px 22px;
         border-radius:9px;text-decoration:none;font-weight:700;font-size:.875rem;">
        View Results in ProfileForge →
      </a>
    </div>

    <!-- Footer -->
    <div style="padding:16px 32px;border-top:1px solid #ede9e3;">
      <p style="font-size:.72rem;color:#a0816a;margin:0;">
        ProfileForge · Multi-Source Candidate Data Transformer<br>
        This is an automated notification.
      </p>
    </div>
  </div>
</body>
</html>"""


def _build_text(
    job_id: str, total: int, processed: int, failed: int,
    missing: int, avg_conf: float, duration: str,
) -> str:
    return f"""ProfileForge — Bulk Processing Complete

Job ID:         {job_id}
Duration:       {duration}

Results:
  Total:          {total}
  Processed:      {processed}
  Failed:         {failed}
  Resume Missing: {missing}
  Avg Confidence: {round(avg_conf * 100)}%

Log in to ProfileForge to view results and download JSON profiles.

---
ProfileForge · Multi-Source Candidate Data Transformer
This is an automated notification.
"""
