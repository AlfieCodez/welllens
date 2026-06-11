"""Tests for subscription gating, comp grants, and Stripe sync."""
import io
from datetime import datetime, timezone
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _register(client, email="u@example.com", username="user1", password="supersecret"):
    return client.post(
        "/register",
        data={
            "name": "Test User",
            "email": email,
            "username": username,
            "password": password,
            "confirm": password,
        },
        follow_redirects=True,
    )


def _make_uploads(app, user_id, n):
    """Create n distinct manual-upload activities for a user (pre-2025 to avoid
    deduping against the test fixture)."""
    from welllens.extensions import db
    from welllens.models import Activity

    with app.app_context():
        for i in range(n):
            db.session.add(
                Activity(
                    user_id=user_id,
                    source="upload",
                    start_time=datetime(2024, 1, 1 + i, tzinfo=timezone.utc),
                    duration_s=1800,
                    distance_m=5000,
                )
            )
        db.session.commit()


def _current_user_id(app):
    from welllens.models import User

    with app.app_context():
        return User.query.filter_by(email="u@example.com").first().id


# --------------------------------------------------------------------------- #
#  is_pro logic
# --------------------------------------------------------------------------- #
def test_is_pro_logic(app):
    from welllens.models import User

    u = User(name="A", email="a@x.com", username="a")
    assert u.is_pro is False
    u.comped = True
    assert u.is_pro is True
    u.comped = False
    u.is_admin = True
    assert u.is_pro is True
    u.is_admin = False
    u.subscription_status = "active"
    assert u.is_pro is True
    u.subscription_status = "canceled"
    assert u.is_pro is False


# --------------------------------------------------------------------------- #
#  Upload gating
# --------------------------------------------------------------------------- #
def test_free_user_blocked_at_limit(client, app):
    _register(client)
    uid = _current_user_id(app)
    _make_uploads(app, uid, 5)  # at the free limit of 5

    gpx = (FIXTURES / "sample.gpx").read_bytes()
    resp = client.post(
        "/upload",
        data={"activity": (io.BytesIO(gpx), "run.gpx")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/billing" in resp.headers["Location"]

    from welllens.models import Activity

    with app.app_context():
        assert Activity.query.filter_by(user_id=uid).count() == 5  # nothing added


def test_pro_user_unlimited(client, app):
    _register(client)
    uid = _current_user_id(app)
    _make_uploads(app, uid, 5)

    from welllens.extensions import db
    from welllens.models import Activity, User

    with app.app_context():
        User.query.get(uid).comped = True  # admin-granted Pro
        db.session.commit()

    gpx = (FIXTURES / "sample.gpx").read_bytes()
    client.post(
        "/upload",
        data={"activity": (io.BytesIO(gpx), "run.gpx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    with app.app_context():
        assert Activity.query.filter_by(user_id=uid).count() == 6  # added past 5


# --------------------------------------------------------------------------- #
#  Admin comp toggle
# --------------------------------------------------------------------------- #
def test_admin_comp_toggle(client, app):
    from welllens.extensions import db
    from welllens.models import User

    _register(client, email="target@x.com", username="target")
    with app.app_context():
        target = User.query.filter_by(email="target@x.com").first()
        tid = target.id
        assert target.comped is False

    # Become admin in-session.
    with client.session_transaction() as sess:
        sess["is_admin"] = True

    client.post(f"/admin/users/{tid}/comp", follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, tid).comped is True
    client.post(f"/admin/users/{tid}/comp", follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, tid).comped is False


# --------------------------------------------------------------------------- #
#  Stripe subscription sync
# --------------------------------------------------------------------------- #
def test_apply_subscription_makes_user_pro(app):
    from welllens.billing import service
    from welllens.extensions import db
    from welllens.models import User

    with app.app_context():
        u = User(name="S", email="s@x.com", username="s", stripe_customer_id="cus_1")
        db.session.add(u)
        db.session.commit()

        service._apply_subscription(
            {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "active",
                "current_period_end": 1893456000,
                "metadata": {},
            }
        )
        u = User.query.filter_by(email="s@x.com").first()
        assert u.plan == "pro"
        assert u.is_pro is True
        assert u.stripe_subscription_id == "sub_1"

        service._apply_subscription(
            {"id": "sub_1", "customer": "cus_1", "status": "canceled", "metadata": {}}
        )
        u = User.query.filter_by(email="s@x.com").first()
        assert u.plan == "free"
        assert u.is_pro is False


def test_stripe_webhook_requires_secret(client, app):
    app.config["STRIPE_WEBHOOK_SECRET"] = ""
    r = client.post("/webhooks/stripe", data="{}", content_type="application/json")
    assert r.status_code == 503
