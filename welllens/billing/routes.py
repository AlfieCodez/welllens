"""Billing routes: upgrade, manage, success/cancel, and the Stripe webhook."""
import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..auth.helpers import current_user, login_required
from ..extensions import csrf
from . import service

log = logging.getLogger(__name__)
billing_bp = Blueprint("billing", __name__)


def _enabled() -> bool:
    cfg = current_app.config
    return bool(cfg.get("STRIPE_SECRET_KEY") and cfg.get("STRIPE_PRICE_ID"))


@billing_bp.route("/billing")
@login_required
def index():
    user = current_user()
    return render_template(
        "billing.html",
        user=user,
        stripe_enabled=_enabled(),
        price_label="£4.99 / month",
        free_limit=current_app.config["FREE_UPLOAD_LIMIT"],
        uploads_used=user.upload_count(),
    )


@billing_bp.route("/billing/checkout", methods=["POST"])
@login_required
def checkout():
    if not _enabled():
        flash("Subscriptions aren't available right now.", "error")
        return redirect(url_for("billing.index"))
    user = current_user()
    if user.is_pro:
        flash("You already have Pro access.", "info")
        return redirect(url_for("billing.index"))
    try:
        url = service.create_checkout_session(user)
    except Exception as exc:  # noqa: BLE001
        log.warning("Stripe checkout failed: %s", exc)
        flash("Couldn't start checkout. Please try again.", "error")
        return redirect(url_for("billing.index"))
    return redirect(url, code=303)


@billing_bp.route("/billing/portal", methods=["POST"])
@login_required
def portal():
    url = service.create_portal_session(current_user())
    if not url:
        flash("No billing account found yet.", "info")
        return redirect(url_for("billing.index"))
    return redirect(url, code=303)


@billing_bp.route("/billing/success")
@login_required
def success():
    # The webhook is the source of truth; this is just a friendly landing page.
    flash("Thanks for subscribing! Your Pro access is being activated.", "success")
    return redirect(url_for("dashboard.index"))


@billing_bp.route("/billing/cancel")
@login_required
def cancel():
    flash("Checkout cancelled — no charge was made.", "info")
    return redirect(url_for("billing.index"))


@billing_bp.route("/webhooks/stripe", methods=["POST"])
@csrf.exempt
def webhook():
    if not current_app.config.get("STRIPE_WEBHOOK_SECRET"):
        log.warning("Stripe webhook hit but STRIPE_WEBHOOK_SECRET is unset.")
        abort(503)
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = service.construct_event(payload, sig)
    except Exception as exc:  # noqa: BLE001 — bad signature / parse error
        log.warning("Stripe webhook verification failed: %s", exc)
        abort(400)

    try:
        service.handle_event(event)
    except Exception as exc:  # noqa: BLE001 — never 500 back to Stripe needlessly
        log.exception("Error handling Stripe event: %s", exc)
    return ("", 200)
