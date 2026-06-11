"""Persist parsed activities with dedupe."""
from datetime import timedelta

from ..extensions import db
from ..models import Activity
from .parsing import ParsedActivity

# Near-identical window for upload dedupe.
_TIME_WINDOW_S = 60
_DURATION_TOLERANCE = 0.02  # 2%


def find_duplicate(user_id: int, parsed: ParsedActivity, external_id: str | None):
    """Return an existing Activity that this one duplicates, or None."""
    # 1) Exact external id match (synced activities).
    if external_id:
        existing = Activity.query.filter_by(
            user_id=user_id, external_id=external_id
        ).first()
        if existing:
            return existing

    # 2) Near-identical start_time + duration for the same user.
    if parsed.start_time is None:
        return None
    lo = parsed.start_time - timedelta(seconds=_TIME_WINDOW_S)
    hi = parsed.start_time + timedelta(seconds=_TIME_WINDOW_S)
    candidates = Activity.query.filter(
        Activity.user_id == user_id,
        Activity.start_time >= lo,
        Activity.start_time <= hi,
    ).all()
    for c in candidates:
        if _durations_match(c.duration_s, parsed.duration_s):
            return c
    return None


def _durations_match(a: int, b: int) -> bool:
    if not a and not b:
        return True
    longest = max(a, b, 1)
    return abs(a - b) / longest <= _DURATION_TOLERANCE


def save_parsed_activity(
    user_id: int,
    parsed: ParsedActivity,
    source: str = "upload",
    raw_path: str | None = None,
    external_id: str | None = None,
) -> tuple[Activity, bool]:
    """Save the activity unless it duplicates an existing one.

    Returns (activity, created). When created is False the returned activity
    is the pre-existing duplicate.
    """
    dupe = find_duplicate(user_id, parsed, external_id)
    if dupe:
        return dupe, False

    activity = Activity(
        user_id=user_id,
        source=source,
        external_id=external_id,
        type=parsed.type,
        start_time=parsed.start_time,
        duration_s=parsed.duration_s,
        distance_m=parsed.distance_m,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        avg_pace=parsed.avg_pace,
        elevation_gain_m=parsed.elevation_gain_m,
        raw_path=raw_path,
    )
    db.session.add(activity)
    db.session.commit()
    return activity, True
