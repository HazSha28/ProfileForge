"""
api/routers/auth_router.py
---------------------------
OAuth authentication routes ported to FastAPI.
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config

router = APIRouter(tags=["Auth"])

# Configure OAuth using environment variables
config = Config(".env")
oauth = OAuth(config)

oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="github",
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "user:email"},
)


@router.get("/google")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo") or await oauth.google.userinfo(request)
    request.session["user"] = {
        "name":     user_info.get("name", ""),
        "email":    user_info.get("email", ""),
        "avatar":   user_info.get("picture", ""),
        "provider": "google",
    }
    return RedirectResponse(url="/")


@router.get("/github")
async def github_login(request: Request):
    redirect_uri = request.url_for("github_callback")
    return await oauth.github.authorize_redirect(request, str(redirect_uri))


@router.get("/github/callback", name="github_callback")
async def github_callback(request: Request):
    await oauth.github.authorize_access_token(request)
    resp = await oauth.github.get("user", request=request)
    profile = resp.json()
    email = profile.get("email", "")
    if not email:
        emails_resp = await oauth.github.get("user/emails", request=request)
        emails = emails_resp.json()
        email = next(
            (e["email"] for e in emails if e.get("primary") and e.get("verified")), ""
        )
    request.session["user"] = {
        "name":     profile.get("name") or profile.get("login", ""),
        "email":    email,
        "avatar":   profile.get("avatar_url", ""),
        "provider": "github",
    }
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
