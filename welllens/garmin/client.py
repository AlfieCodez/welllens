"""Garmin API client: keep tokens fresh and pull activity files."""
from __future__ import annotations

import requests

from ..extensions import db
from ..models import GarminToken
from . import oauth

_TIMEOUT_S = 20


def get_valid_access_token(token: GarminToken) -> str:
    """Return a usable access token, refreshing it first if it has expired."""
    if token.is_expired() and token.refresh_token:
        data = oauth.refresh_tokens(token.refresh_token)
        token.access_token = data["access_token"]
        token.refresh_token = data.get("refresh_token", token.refresh_token)
        token.expires_at = oauth.expiry_from(data.get("expires_in"))
        token.refresh_expires_at = oauth.expiry_from(data.get("refresh_token_expires_in"))
        token.scope = data.get("scope", token.scope)
        db.session.commit()
    return token.access_token


def pull_file(callback_url: str, access_token: str) -> bytes:
    """Download an activity file from a Garmin callback/file URL."""
    resp = requests.get(
        callback_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.content


def sniff_extension(data: bytes, hint: str | None = None) -> str:
    """Guess the activity file type from a type hint or the bytes themselves."""
    if hint:
        h = hint.lower()
        if "gpx" in h:
            return ".gpx"
        if "tcx" in h:
            return ".tcx"
        if "fit" in h:
            return ".fit"

    head = data[:512].lstrip()
    if head[:5].lower() == b"<?xml" or head[:1] == b"<":
        text = head.lower()
        if b"trainingcenterdatabase" in text:
            return ".tcx"
        if b"gpx" in text:
            return ".gpx"
    # .FIT files start with a header whose bytes 8-12 are the ".FIT" signature.
    if len(data) >= 12 and data[8:12] == b".FIT":
        return ".fit"
    return ".fit"  # sensible default for Garmin
