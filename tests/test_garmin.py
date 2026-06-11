"""Tests for the Garmin Connect integration (OAuth2 PKCE + webhook ingest)."""
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from welllens.garmin import client, oauth

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SECRET = "test-webhook-secret"


# --------------------------------------------------------------------------- #
#  PKCE
# --------------------------------------------------------------------------- #
def test_code_verifier_length_in_range():
    v = oauth.make_code_verifier()
    assert 43 <= len(v) <= 128


def test_code_challenge_is_s256_base64url():
    v = "test-verifier-value-1234567890-abcdefghij"
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert oauth.code_challenge_for(v) == expected
    assert "=" not in oauth.code_challenge_for(v)


def test_build_authorize_url(app):
    with app.app_context():
        app.config["GARMIN_CLIENT_ID"] = "client-abc"
        v = oauth.make_code_verifier()
        url = oauth.build_authorize_url("https://x.test/cb", v, "state123")
    assert url.startswith("https://apis.garmin.com/tools/oauth2/authorizeUser?")
    assert "client_id=client-abc" in url
    assert "code_challenge_method=S256" in url
    assert "state=state123" in url
    assert oauth.code_challenge_for(v) in url


# --------------------------------------------------------------------------- #
#  Webhook authentication
# --------------------------------------------------------------------------- #
def test_webhook_get_is_health_ok(client_app):
    app, c = client_app
    r = c.get("/webhooks/garmin")
    assert r.status_code == 200


def test_webhook_rejects_without_token(client_app):
    app, c = client_app
    app.config["GARMIN_WEBHOOK_TOKEN"] = ""  # unverifiable
    r = c.post("/webhooks/garmin", json={})
    assert r.status_code == 503


def test_webhook_rejects_wrong_token(client_app):
    app, c = client_app
    app.config["GARMIN_WEBHOOK_TOKEN"] = SECRET
    r = c.post("/webhooks/garmin?token=nope", json={})
    assert r.status_code == 403


def test_webhook_accepts_correct_token(client_app):
    app, c = client_app
    app.config["GARMIN_WEBHOOK_TOKEN"] = SECRET
    r = c.post(f"/webhooks/garmin?token={SECRET}", json={})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
#  Ping -> pull -> parse -> dedupe
# --------------------------------------------------------------------------- #
def test_webhook_ingests_and_dedupes(client_app, monkeypatch, tmp_path):
    app, c = client_app
    app.config["GARMIN_WEBHOOK_TOKEN"] = SECRET
    app.config["UPLOAD_DIR"] = tmp_path

    from welllens.extensions import db
    from welllens.models import Activity, GarminToken, User

    with app.app_context():
        user = User(name="G", email="g@example.com", username="garminuser")
        db.session.add(user)
        db.session.commit()
        token = GarminToken(
            user_id=user.id,
            garmin_user_id="G123",
            access_token="fake-access",
            refresh_token="fake-refresh",
            expires_at=datetime(2999, 1, 1, tzinfo=timezone.utc),  # not expired
        )
        db.session.add(token)
        db.session.commit()
        user_id = user.id

    # Mock the actual download — return our GPX fixture bytes.
    gpx_bytes = (FIXTURES / "sample.gpx").read_bytes()
    monkeypatch.setattr(client, "pull_file", lambda url, tok: gpx_bytes)

    ping = {
        "activityFiles": [
            {
                "userId": "G123",
                "callbackURL": "https://apis.garmin.com/wellness-api/rest/activityFile?id=1",
                "summaryId": "SUMMARY-1",
                "fileType": "GPX",
            }
        ]
    }

    r1 = c.post(f"/webhooks/garmin?token={SECRET}", json=ping)
    assert r1.status_code == 200
    with app.app_context():
        acts = Activity.query.filter_by(user_id=user_id).all()
        assert len(acts) == 1
        assert acts[0].source == "garmin"
        assert acts[0].external_id == "SUMMARY-1"

    # Same summaryId again -> deduped, still one activity.
    r2 = c.post(f"/webhooks/garmin?token={SECRET}", json=ping)
    assert r2.status_code == 200
    with app.app_context():
        assert Activity.query.filter_by(user_id=user_id).count() == 1


def test_webhook_ignores_unknown_garmin_user(client_app, monkeypatch, tmp_path):
    app, c = client_app
    app.config["GARMIN_WEBHOOK_TOKEN"] = SECRET
    app.config["UPLOAD_DIR"] = tmp_path
    monkeypatch.setattr(client, "pull_file", lambda url, tok: b"should-not-be-called")

    ping = {
        "activityFiles": [
            {"userId": "UNKNOWN", "callbackURL": "https://x", "summaryId": "S"}
        ]
    }
    r = c.post(f"/webhooks/garmin?token={SECRET}", json=ping)
    assert r.status_code == 200  # still a quick 200, just nothing ingested


def test_sniff_extension():
    assert client.sniff_extension(b"", hint="GPX") == ".gpx"
    assert client.sniff_extension(b"", hint="TCX") == ".tcx"
    assert client.sniff_extension(b"<?xml version='1.0'?><gpx>") == ".gpx"
    assert client.sniff_extension(
        b"<?xml version='1.0'?><TrainingCenterDatabase>"
    ) == ".tcx"
    assert client.sniff_extension(b"\x0e\x10\x98\x00\x00\x00\x00\x00.FITxxx") == ".fit"
