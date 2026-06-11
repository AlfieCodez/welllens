"""Top-level routes."""
from flask import Blueprint, current_app, redirect, render_template, send_from_directory, url_for

from ..auth.helpers import current_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@main_bp.route("/healthz")
def healthz():
    return {"status": "ok"}


@main_bp.route("/offline")
def offline():
    # Served by the service worker as the offline fallback for navigations.
    return render_template("offline.html")


@main_bp.route("/sw.js")
def service_worker():
    # Served from root so the service worker controls the whole "/" scope.
    resp = send_from_directory(current_app.static_folder, "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp
