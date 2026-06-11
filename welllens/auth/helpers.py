"""Session helpers and route guards."""
from functools import wraps

from flask import flash, g, redirect, session, url_for

from ..extensions import db
from ..models import User


def login_user(user: User) -> None:
    session["user_id"] = user.id
    session.permanent = True


def logout_user() -> None:
    session.pop("user_id", None)
    session.pop("is_admin", None)


def current_user() -> User | None:
    """Return the logged-in User, cached on the request via flask.g."""
    if "user_id" not in session:
        return None
    if not hasattr(g, "_current_user"):
        g._current_user = db.session.get(User, session["user_id"])
    return g._current_user


def is_admin() -> bool:
    return bool(session.get("is_admin"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # Admin session is set server-side only, after the allowlist check.
        if not is_admin():
            flash("Admin access required.", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped
