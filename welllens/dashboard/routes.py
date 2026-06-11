"""User and admin dashboards."""
from flask import Blueprint, flash, redirect, render_template, url_for

from ..auth.helpers import admin_required, current_user, login_required
from ..extensions import db
from ..models import Activity, GarminToken, SupportTicket, User
from ..insights.compute import compute_insights
from ..insights.narrate import narrate

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    user = current_user()
    activities = (
        Activity.query.filter_by(user_id=user.id)
        .order_by(Activity.start_time.desc())
        .all()
    )
    insights = compute_insights(activities)
    insight_text = narrate(insights)

    chart = _chart_data(insights, activities)
    recent = activities[:10]
    garmin_linked = (
        GarminToken.query.filter_by(user_id=user.id).first() is not None
    )
    return render_template(
        "dashboard.html",
        user=user,
        activities=recent,
        insights=insights,
        insight_text=insight_text,
        chart=chart,
        garmin_linked=garmin_linked,
    )


def _chart_data(insights, activities) -> dict:
    # Weekly distance (km) for the bar chart.
    weekly_labels = [b.week_start.strftime("%d %b") for b in insights.weekly]
    weekly_km = [b.distance_km for b in insights.weekly]

    # Pace-at-HR points over time for the trend line (oldest -> newest).
    pace_points = [
        {
            "t": a.start_time.strftime("%d %b"),
            "pace": round(a.avg_pace / 60, 2),  # minutes/km for readability
        }
        for a in sorted(activities, key=lambda x: x.start_time)
        if a.avg_pace
    ]
    return {
        "weekly_labels": weekly_labels,
        "weekly_km": weekly_km,
        "pace_labels": [p["t"] for p in pace_points],
        "pace_values": [p["pace"] for p in pace_points],
    }


@dashboard_bp.route("/admin")
@admin_required
def admin():
    user_count = db.session.query(User).count()
    activity_count = db.session.query(Activity).count()
    admin_count = db.session.query(User).filter_by(is_admin=True).count()

    pro_count = sum(1 for u in User.query.all() if u.is_pro)
    open_tickets = SupportTicket.query.filter_by(resolved=False).count()

    users = User.query.order_by(User.created_at.desc()).all()
    rows = [
        {
            "user": u,
            "activity_count": Activity.query.filter_by(user_id=u.id).count(),
        }
        for u in users
    ]
    return render_template(
        "admin.html",
        user=current_user(),
        rows=rows,
        user_count=user_count,
        activity_count=activity_count,
        admin_count=admin_count,
        pro_count=pro_count,
        open_tickets=open_tickets,
    )


@dashboard_bp.route("/admin/users/<int:user_id>/comp", methods=["POST"])
@admin_required
def toggle_comp(user_id):
    target = db.session.get(User, user_id)
    if target is None:
        flash("User not found.", "error")
        return redirect(url_for("dashboard.admin"))
    target.comped = not target.comped
    db.session.commit()
    state = "granted free Pro to" if target.comped else "removed free Pro from"
    flash(f"{state} {target.email}.", "success")
    return redirect(url_for("dashboard.admin"))
