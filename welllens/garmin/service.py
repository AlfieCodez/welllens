"""Garmin service layer: persist tokens and ingest pushed/pulled activities."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from flask import current_app

from ..activities.parsing import ActivityParseError, parse_file
from ..activities.service import save_parsed_activity
from ..extensions import db
from ..models import GarminToken
from . import client, oauth

log = logging.getLogger(__name__)

# Keys a Garmin notification might use for the list of activities.
_LIST_KEYS = ("activityFiles", "activities", "activityDetails", "activityFileNotifications")


def save_token(user_id: int, token_response: dict, garmin_user_id: str | None) -> GarminToken:
    """Create or update the GarminToken for a user (one link per user)."""
    token = GarminToken.query.filter_by(user_id=user_id).first()
    if token is None:
        token = GarminToken(user_id=user_id)
        db.session.add(token)

    token.access_token = token_response["access_token"]
    token.refresh_token = token_response.get("refresh_token", token.refresh_token)
    token.token_type = token_response.get("token_type", "Bearer")
    token.scope = token_response.get("scope", token.scope)
    token.expires_at = oauth.expiry_from(token_response.get("expires_in"))
    token.refresh_expires_at = oauth.expiry_from(
        token_response.get("refresh_token_expires_in")
    )
    if garmin_user_id:
        token.garmin_user_id = str(garmin_user_id)
    db.session.commit()
    return token


def disconnect(user_id: int) -> bool:
    token = GarminToken.query.filter_by(user_id=user_id).first()
    if token is None:
        return False
    db.session.delete(token)
    db.session.commit()
    return True


def process_notification(payload: dict) -> dict:
    """Ingest a Garmin ping/push payload. Returns a summary of what happened.

    Designed to never raise — the webhook must always return a quick 200.
    """
    result = {"added": 0, "skipped": 0, "errors": 0, "ignored": 0, "deregistered": 0}

    # Handle user deregistrations (revoked access).
    for dereg in payload.get("deregistrations", []) or []:
        gid = str(dereg.get("userId") or "")
        token = GarminToken.query.filter_by(garmin_user_id=gid).first() if gid else None
        if token:
            db.session.delete(token)
            db.session.commit()
            result["deregistered"] += 1

    for item in _iter_items(payload):
        try:
            _ingest_one(item, result)
        except Exception as exc:  # noqa: BLE001 — keep the webhook resilient
            log.warning("Garmin ingest error: %s", exc)
            result["errors"] += 1

    return result


def _iter_items(payload: dict):
    for key in _LIST_KEYS:
        items = payload.get(key)
        if isinstance(items, list):
            yield from items


def _ingest_one(item: dict, result: dict) -> None:
    garmin_user_id = str(item.get("userId") or "")
    callback_url = item.get("callbackURL") or item.get("callbackUrl")
    external_id = str(
        item.get("summaryId")
        or item.get("activityId")
        or item.get("fileId")
        or item.get("summaryid")
        or ""
    ) or None
    file_type = item.get("fileType") or item.get("activityFileType")

    if not (garmin_user_id and callback_url):
        result["ignored"] += 1
        return

    token = GarminToken.query.filter_by(garmin_user_id=garmin_user_id).first()
    if token is None:
        # We don't know this Garmin user — nothing to attach the activity to.
        result["ignored"] += 1
        return

    access_token = client.get_valid_access_token(token)
    data = client.pull_file(callback_url, access_token)
    ext = client.sniff_extension(data, hint=file_type)

    dest = Path(current_app.config["UPLOAD_DIR"]) / f"garmin_{uuid.uuid4().hex}{ext}"
    dest.write_bytes(data)

    try:
        parsed = parse_file(dest)
    except ActivityParseError:
        dest.unlink(missing_ok=True)
        result["errors"] += 1
        return

    _activity, created = save_parsed_activity(
        token.user_id,
        parsed,
        source="garmin",
        raw_path=str(dest),
        external_id=external_id,
    )
    if created:
        result["added"] += 1
    else:
        dest.unlink(missing_ok=True)
        result["skipped"] += 1
