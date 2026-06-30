"""
auth_oauth.py
-------------
Google and GitHub OAuth 2.0 integration using Authlib.

Flow:
  1. User clicks "Google" or "GitHub" on the login page.
  2. Browser redirects to /auth/google or /auth/github.
  3. We redirect to the provider's authorization URL.
  4. Provider redirects back to /auth/google/callback or /auth/github/callback.
  5. We exchange the code for an access token, fetch the user profile,
     create a session, and redirect to the main app.
"""

from __future__ import annotations

import os
from flask import Blueprint, redirect, session, url_for, request
from authlib.integrations.flask_client import OAuth

oauth_bp = Blueprint("oauth", __name__)
oauth    = OAuth()


def init_oauth(app):
    """Register OAuth providers on the Flask app."""
    oauth.init_app(app)

    # ── Google ──────────────────────────────────────────────────
    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    # ── GitHub ──────────────────────────────────────────────────
    oauth.register(
        name="github",
        client_id=os.environ.get("GITHUB_CLIENT_ID"),
        client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),
        access_token_url="https://github.com/login/oauth/access_token",
        access_token_params=None,
        authorize_url="https://github.com/login/oauth/authorize",
        authorize_params=None,
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )


# ── Google routes ────────────────────────────────────────────────

@oauth_bp.route("/auth/google")
def google_login():
    redirect_uri = url_for("oauth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@oauth_bp.route("/auth/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    user_info = token.get("userinfo")
    if not user_info:
        user_info = oauth.google.userinfo()

    session["user"] = {
        "name":     user_info.get("name", ""),
        "email":    user_info.get("email", ""),
        "avatar":   user_info.get("picture", ""),
        "provider": "google",
    }
    return redirect("/")


# ── GitHub routes ────────────────────────────────────────────────

@oauth_bp.route("/auth/github")
def github_login():
    redirect_uri = url_for("oauth.github_callback", _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@oauth_bp.route("/auth/github/callback")
def github_callback():
    oauth.github.authorize_access_token()

    # Fetch basic profile
    resp = oauth.github.get("user")
    profile = resp.json()

    # GitHub may not expose email publicly — fetch from /user/emails
    email = profile.get("email")
    if not email:
        emails_resp = oauth.github.get("user/emails")
        emails = emails_resp.json()
        primary = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        email = primary or ""

    session["user"] = {
        "name":     profile.get("name") or profile.get("login", ""),
        "email":    email,
        "avatar":   profile.get("avatar_url", ""),
        "provider": "github",
    }
    return redirect("/")


# ── Logout ───────────────────────────────────────────────────────

@oauth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
