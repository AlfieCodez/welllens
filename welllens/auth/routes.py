"""Authentication routes: email/password, Google OAuth, admin allowlist."""
import re

from authlib.integrations.flask_client import OAuthError
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..extensions import db, oauth
from ..models import User
from .google import google_enabled
from .helpers import current_user, login_user, logout_user

auth_bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _render_auth(active_view: str = "signin"):
    return render_template(
        "auth.html", active_view=active_view, google_enabled=google_enabled()
    )


# --------------------------------------------------------------------------- #
#  Email / password
# --------------------------------------------------------------------------- #
@auth_bp.route("/login", methods=["GET"])
def login():
    if current_user():
        return redirect(url_for("dashboard.index"))
    return _render_auth("signin")


@auth_bp.route("/login", methods=["POST"])
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        # Same message either way — don't reveal which field was wrong.
        flash("Incorrect email or password.", "login_error")
        return _render_auth("signin"), 401

    login_user(user)
    # TEMPORARY dev bypass: let an admin user reach /admin via password login,
    # until Google OAuth is configured. Controlled by ALLOW_PASSWORD_ADMIN.
    if user.is_admin and current_app.config.get("ALLOW_PASSWORD_ADMIN"):
        session["is_admin"] = True
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/register", methods=["POST"])
def register():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""

    error = _validate_registration(name, email, username, password, confirm)
    if error:
        flash(error, "register_error")
        return _render_auth("register"), 400

    user = User(name=name, email=email, username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return redirect(url_for("dashboard.index"))


def _validate_registration(name, email, username, password, confirm) -> str | None:
    if not name:
        return "Please enter your name."
    if not EMAIL_RE.match(email):
        return "Please enter a valid email address."
    if not USERNAME_RE.match(username):
        return "Username must be at least 3 letters, numbers or underscores."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Those passwords don't match. Try again."
    if User.query.filter_by(email=email).first():
        return "An account with that email already exists."
    if User.query.filter_by(username=username).first():
        return "That username is taken. Try another."
    return None


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("You've been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password")
def forgot_password():
    # Stub for Phase 1 — real reset flow comes later.
    return render_template("forgot_password.html")


# --------------------------------------------------------------------------- #
#  Google OAuth — user sign-in / sign-up
# --------------------------------------------------------------------------- #
@auth_bp.route("/auth/google")
def google_login():
    if not google_enabled():
        flash("Google sign-in isn't configured on this server.", "login_error")
        return _render_auth("signin")
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    info = _complete_google()
    if info is None:
        return _render_auth("signin"), 400

    user = _find_or_create_google_user(info)
    login_user(user)
    return redirect(url_for("dashboard.index"))


# --------------------------------------------------------------------------- #
#  Google OAuth — admin (server-enforced allowlist)
# --------------------------------------------------------------------------- #
@auth_bp.route("/admin/auth/google")
def admin_google_login():
    if not google_enabled():
        flash("Google sign-in isn't configured on this server.", "login_error")
        return _render_auth("admin")
    redirect_uri = url_for("auth.admin_google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/admin/auth/google/callback")
def admin_google_callback():
    info = _complete_google()
    if info is None:
        return _render_auth("admin"), 400

    email = (info.get("email") or "").strip().lower()
    verified = info.get("email_verified", False)
    allowlist = current_app.config["ADMIN_EMAILS"]

    # The client cannot be trusted: enforce admin entirely here.
    if not verified or email not in allowlist:
        flash("That account isn't authorised for admin access.", "login_error")
        return _render_auth("admin"), 403

    user = _find_or_create_google_user(info)
    user.is_admin = True
    db.session.commit()

    login_user(user)
    session["is_admin"] = True
    return redirect(url_for("dashboard.admin"))


# --------------------------------------------------------------------------- #
#  Google helpers
# --------------------------------------------------------------------------- #
def _complete_google() -> dict | None:
    """Exchange the code for tokens and return verified userinfo, or None."""
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError:
        flash("Google sign-in was cancelled or failed.", "login_error")
        return None
    info = token.get("userinfo")
    if not info or not info.get("email"):
        flash("Google didn't return an email address.", "login_error")
        return None
    return info


def _find_or_create_google_user(info: dict) -> User:
    sub = info.get("sub")
    email = (info.get("email") or "").strip().lower()
    name = info.get("name") or email.split("@")[0]

    user = User.query.filter_by(google_sub=sub).first()
    if user:
        return user

    # Link to an existing email account if one exists.
    user = User.query.filter_by(email=email).first()
    if user:
        user.google_sub = sub
        db.session.commit()
        return user

    user = User(name=name, email=email, google_sub=sub, username=None)
    db.session.add(user)
    db.session.commit()
    return user
