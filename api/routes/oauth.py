"""
api/routes/oauth.py
-------------------
Google and GitHub OAuth 2.0 for FastAPI using Authlib.

FastAPI uses Request objects directly instead of Flask's thread-local
`request` proxy — so we pass `request: Request` explicitly to every route.
Sessions are provided by Starlette's SessionMiddleware.
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

router = APIRouter(tags=["auth"])

# ---------------------------------------------------------------------------
# OAuth client registry
# ---------------------------------------------------------------------------
oauth = OAuth()

oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

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


# ---------------------------------------------------------------------------
# Google routes
# ---------------------------------------------------------------------------

@router.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = str(request.url_for("google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo") or await oauth.google.userinfo(token=token)

    request.session["user"] = {
        "name":     user_info.get("name", ""),
        "email":    user_info.get("email", ""),
        "avatar":   user_info.get("picture", ""),
        "provider": "google",
    }
    return RedirectResponse(url="/dashboard")


# ---------------------------------------------------------------------------
# GitHub routes
# ---------------------------------------------------------------------------

@router.get("/auth/github")
async def github_login(request: Request):
    redirect_uri = str(request.url_for("github_callback"))
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/auth/github/callback", name="github_callback")
async def github_callback(request: Request):
    await oauth.github.authorize_access_token(request)

    resp = await oauth.github.get("user", token=request.session.get("github_token"))
    profile = resp.json()

    email = profile.get("email")
    if not email:
        emails_resp = await oauth.github.get("user/emails")
        emails = emails_resp.json()
        primary = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")),
            None,
        )
        email = primary or ""

    request.session["user"] = {
        "name":     profile.get("name") or profile.get("login", ""),
        "email":    email,
        "avatar":   profile.get("avatar_url", ""),
        "provider": "github",
    }
    return RedirectResponse(url="/dashboard")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
