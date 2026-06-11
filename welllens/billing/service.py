"""Stripe billing: customers, checkout, portal, and webhook handling.

All Stripe secret-key usage is server-side. Card data never touches WellLens —
Stripe Checkout (hosted) collects it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from flask import current_app, url_for

from ..extensions import db
from ..models import User

log = logging.getLogger(__name__)


def _init_stripe() -> None:
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]


def _ts_to_dt(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def get_or_create_customer(user: User) -> str:
    """Return the user's Stripe customer id, creating one if needed."""
    _init_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email,
        name=user.name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer["id"]
    db.session.commit()
    return customer["id"]


def create_checkout_session(user: User) -> str:
    """Create a subscription Checkout Session and return its URL."""
    _init_stripe()
    customer_id = get_or_create_customer(user)
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=str(user.id),
        line_items=[{"price": current_app.config["STRIPE_PRICE_ID"], "quantity": 1}],
        success_url=url_for("billing.success", _external=True)
        + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=url_for("billing.cancel", _external=True),
        allow_promotion_codes=True,
        metadata={"user_id": str(user.id)},
    )
    return session["url"]


def create_portal_session(user: User) -> str | None:
    """Create a Stripe customer-portal session (manage/cancel)."""
    _init_stripe()
    if not user.stripe_customer_id:
        return None
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=url_for("billing.index", _external=True),
    )
    return session["url"]


# --------------------------------------------------------------------------- #
#  Webhook
# --------------------------------------------------------------------------- #
def construct_event(payload: bytes, sig_header: str):
    """Verify and parse a Stripe webhook event. Raises on bad signature."""
    _init_stripe()
    secret = current_app.config["STRIPE_WEBHOOK_SECRET"]
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def handle_event(event) -> None:
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        _on_checkout_completed(obj)
    elif etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _apply_subscription(obj)
    else:
        log.debug("Unhandled Stripe event: %s", etype)


def _on_checkout_completed(session) -> None:
    user = _user_for(session.get("client_reference_id"), session.get("customer"))
    if not user:
        return
    if session.get("customer"):
        user.stripe_customer_id = session["customer"]
    sub_id = session.get("subscription")
    if sub_id:
        user.stripe_subscription_id = sub_id
        _init_stripe()
        sub = stripe.Subscription.retrieve(sub_id)
        _apply_subscription(sub)
    else:
        db.session.commit()


def _apply_subscription(sub) -> None:
    """Sync a Stripe subscription object onto the matching user."""
    customer_id = sub.get("customer")
    user = _user_for(
        (sub.get("metadata") or {}).get("user_id"), customer_id, sub.get("id")
    )
    if not user:
        log.warning("No user for Stripe subscription %s", sub.get("id"))
        return

    status = sub.get("status")
    user.stripe_subscription_id = sub.get("id")
    if customer_id:
        user.stripe_customer_id = customer_id
    user.subscription_status = status
    user.subscription_current_period_end = _ts_to_dt(sub.get("current_period_end"))
    user.plan = "pro" if status in ("active", "trialing") else "free"
    db.session.commit()
    log.info("User %s subscription -> %s (%s)", user.id, status, user.plan)


def _user_for(user_id, customer_id=None, subscription_id=None) -> User | None:
    if user_id:
        u = db.session.get(User, int(user_id))
        if u:
            return u
    if customer_id:
        u = User.query.filter_by(stripe_customer_id=customer_id).first()
        if u:
            return u
    if subscription_id:
        return User.query.filter_by(stripe_subscription_id=subscription_id).first()
    return None
