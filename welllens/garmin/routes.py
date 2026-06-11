"""Garmin Connect linking + webhook receiver."""
import hmac
import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    request,
    session,
    url_for,
)

from ..auth.helpers import current_user, login_required
from ..extensions import csrf
from . import oauth, service

log = logging.getLogger(__name__)
garmin_bp = Blueprint("garmin", __name__)

_SESSION_VERIFIER = "garmin_pkce_verifier"
_SESSION_STATE = "garmin_oauth_state"


def _redirect_uri() -> str:
    """The OAuth2 redirect URI. Prefer the configured value (must match what's
    registered with Garmin); otherwise build an HTTPS URL from the request."""
    configured = current_app.config.get("GARMIN_REDIRECT_URI")
    if configured:
        return configured
    return url_for("garmin.callback", _external=True, _scheme="https")


# --------------------------------------------------------------------------- #
#  Account linking (OAuth 2.0 PKCE)
# --------------------------------------------------------------------------- #
@garmin_bp.route("/connect/garmin")
@login_required
def connect():
    if not _enabled():
        flash("Garmin sync isn't configured on this server.", "error")
        return redirect(url_for("dashboard.index"))

    verifier = oauth.make_code_verifier()
    state = oauth.make_state()
    session[_SESSION_VERIFIER] = verifier
    session[_SESSION_STATE] = state

    url = oauth.build_authorize_url(_redirect_uri(), verifier, state)
    return redirect(url)


@garmin_bp.route("/connect/garmin/callback")
@login_required
def callback():
    user = current_user()
    error = request.args.get("error")
    if error:
        flash(f"Garmin connection was cancelled ({error}).", "error")
        return redirect(url_for("dashboard.index"))

    state = request.args.get("state")
    code = request.args.get("code")
    expected_state = session.pop(_SESSION_STATE, None)
    verifier = session.pop(_SESSION_VERIFIER, None)

    if not code or not state or state != expected_state or not verifier:
        flash("Garmin connection failed (invalid response). Please try again.", "error")
        return redirect(url_for("dashboard.index"))

    try:
        token_response = oauth.exchange_code(code, verifier, _redirect_uri())
        garmin_user_id = oauth.fetch_user_id(token_response["access_token"])
        service.save_token(user.id, token_response, garmin_user_id)
    except oauth.GarminAuthError as exc:
        log.warning("Garmin token exchange failed: %s", exc)
        flash("Couldn't complete the Garmin connection. Please try again.", "error")
        return redirect(url_for("dashboard.index"))

    flash("Garmin connected. New activities will sync automatically.", "success")
    return redirect(url_for("dashboard.index"))


@garmin_bp.route("/connect/garmin/disconnect", methods=["POST"])
@login_required
def disconnect():
    if service.disconnect(current_user().id):
        flash("Garmin disconnected.", "info")
    return redirect(url_for("dashboard.index"))


# --------------------------------------------------------------------------- #
#  Webhook receiver (Garmin ping/push)
# --------------------------------------------------------------------------- #
@garmin_bp.route("/webhooks/garmin", methods=["GET", "POST"])
@csrf.exempt
def webhook():
    # GET is used by some setups to verify the endpoint is alive.
    if request.method == "GET":
        return ("WellLens Garmin webhook OK", 200)

    _verify_caller()

    payload = request.get_json(silent=True) or {}
    summary = service.process_notification(payload)
    log.info("Garmin webhook processed: %s", summary)

    # Always return a quick 200 so Garmin doesn't retry/queue unnecessarily.
    return ("", 200)


def _verify_caller() -> None:
    """Authenticate the webhook via a shared secret in the URL.

    Garmin doesn't HMAC-sign pings, so the standard approach is to register a
    callback URL containing a hard-to-guess token and check it here. We also
    only ever act on data we then *pull* from Garmin's own domain.
    """
    expected = current_app.config.get("GARMIN_WEBHOOK_TOKEN")
    if not expected:
        # No secret configured -> we can't verify authenticity; refuse.
        log.warning("Garmin webhook hit but GARMIN_WEBHOOK_TOKEN is unset.")
        abort(503)
    provided = request.args.get("token", "")
    if not hmac.compare_digest(provided, expected):
        abort(403)


def _enabled() -> bool:
    cfg = current_app.config
    return bool(cfg.get("GARMIN_CLIENT_ID") and cfg.get("GARMIN_CLIENT_SECRET"))
