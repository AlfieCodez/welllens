"""Garmin Connect OAuth 2.0 PKCE flow.

Endpoints (current as of 2026; OAuth 1.0a retires 31 Dec 2026):
  authorize: https://apis.garmin.com/tools/oauth2/authorizeUser
  token:     https://diauth.garmin.com/di-oauth2-service/oauth/token

All signing/secret handling happens server-side.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from flask import current_app

_TIMEOUT_S = 15


# --------------------------------------------------------------------------- #
#  PKCE helpers
# --------------------------------------------------------------------------- #
def make_code_verifier() -> str:
    """A high-entropy code_verifier (RFC 7636: 43-128 chars, URL-safe)."""
    return secrets.token_urlsafe(64)[:96]


def code_challenge_for(verifier: str) -> str:
    """S256 challenge = base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_state() -> str:
    return secrets.token_urlsafe(24)


# --------------------------------------------------------------------------- #
#  Authorization URL
# --------------------------------------------------------------------------- #
def build_authorize_url(redirect_uri: str, code_verifier: str, state: str) -> str:
    cfg = current_app.config
    params = {
        "response_type": "code",
        "client_id": cfg["GARMIN_CLIENT_ID"],
        "code_challenge": code_challenge_for(code_verifier),
        "code_challenge_method": "S256",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    scope = cfg.get("GARMIN_SCOPE")
    if scope:
        params["scope"] = scope
    return f"{cfg['GARMIN_AUTH_URL']}?{urlencode(params)}"


# --------------------------------------------------------------------------- #
#  Token exchange / refresh
# --------------------------------------------------------------------------- #
class GarminAuthError(Exception):
    """Raised when an OAuth token request fails."""


def exchange_code(code: str, code_verifier: str, redirect_uri: str) -> dict:
    cfg = current_app.config
    data = {
        "grant_type": "authorization_code",
        "client_id": cfg["GARMIN_CLIENT_ID"],
        "client_secret": cfg["GARMIN_CLIENT_SECRET"],
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    return _token_request(data)


def refresh_tokens(refresh_token: str) -> dict:
    cfg = current_app.config
    data = {
        "grant_type": "refresh_token",
        "client_id": cfg["GARMIN_CLIENT_ID"],
        "client_secret": cfg["GARMIN_CLIENT_SECRET"],
        "refresh_token": refresh_token,
    }
    return _token_request(data)


def _token_request(data: dict) -> dict:
    cfg = current_app.config
    try:
        resp = requests.post(
            cfg["GARMIN_TOKEN_URL"],
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise GarminAuthError(f"Garmin token request failed: {exc}") from exc
    if resp.status_code != 200:
        raise GarminAuthError(
            f"Garmin token endpoint returned {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


def expiry_from(seconds: int | None) -> datetime | None:
    if not seconds:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))


def fetch_user_id(access_token: str) -> str | None:
    """Resolve the Garmin user id for a freshly-issued access token."""
    cfg = current_app.config
    try:
        resp = requests.get(
            cfg["GARMIN_USER_ID_URL"],
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None
    data = resp.json()
    return data.get("userId") or data.get("userID") or data.get("id")
