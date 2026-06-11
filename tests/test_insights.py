"""Tests for the insights compute engine and dedupe logic."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from welllens.insights.compute import (
    _acwr_flag,
    activity_load,
    compute_insights,
)

NOW = datetime(2025, 6, 30, 12, 0, tzinfo=timezone.utc)  # a Monday


def make_activity(days_ago, duration_s=1800, distance_m=5000, avg_hr=140, avg_pace=360):
    return SimpleNamespace(
        start_time=NOW - timedelta(days=days_ago),
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        avg_pace=avg_pace,
    )


def test_empty_insights():
    ins = compute_insights([], now=NOW)
    assert ins.total_activities == 0
    assert ins.acwr is None
    assert ins.acwr_flag == "unknown"


def test_acwr_flag_thresholds():
    assert _acwr_flag(0.5) == "low"
    assert _acwr_flag(1.0) == "balanced"
    assert _acwr_flag(1.3) == "balanced"
    assert _acwr_flag(1.4) == "watch"
    assert _acwr_flag(2.0) == "high"


def test_activity_load_uses_hr():
    # With HR=140 (the reference), load == minutes.
    assert activity_load(3600, 140) == pytest.approx(60.0)
    # Without HR, falls back to raw minutes.
    assert activity_load(3600, None) == pytest.approx(60.0)
    # Higher HR -> higher load.
    assert activity_load(3600, 168) > activity_load(3600, 140)


def test_acwr_balanced_when_consistent():
    # Same load every few days for 4 weeks -> acute ~= chronic -> ~balanced.
    acts = [make_activity(d) for d in (1, 4, 8, 11, 15, 18, 22, 25)]
    ins = compute_insights(acts, now=NOW)
    assert ins.acwr is not None
    assert ins.acwr_flag in ("low", "balanced", "watch")


def test_acwr_high_on_spike():
    # Lots of recent load, little before -> high ratio.
    recent = [make_activity(d, duration_s=3600) for d in (0, 1, 2, 3, 4)]
    old = [make_activity(d, duration_s=600) for d in (21, 24, 27)]
    ins = compute_insights(recent + old, now=NOW)
    assert ins.acwr_flag == "high"


def test_weekly_buckets_and_wow():
    # 10km this week, 5km last week -> +100%.
    acts = [
        make_activity(0, distance_m=10000),
        make_activity(7, distance_m=5000),
    ]
    ins = compute_insights(acts, now=NOW)
    assert ins.this_week_km == pytest.approx(10.0)
    assert ins.last_week_km == pytest.approx(5.0)
    assert ins.wow_distance_pct == pytest.approx(100.0)


def test_pace_trend_improving():
    # Later sessions faster (lower pace) at same HR -> improving.
    acts = []
    for i, days in enumerate((28, 24, 20, 16, 8, 4)):
        pace = 400 - i * 10  # getting faster over time
        acts.append(make_activity(days, avg_pace=pace, avg_hr=150))
    ins = compute_insights(acts, now=NOW)
    assert ins.pace_trend == "improving"


def test_pace_trend_insufficient_data():
    acts = [make_activity(1), make_activity(3)]
    ins = compute_insights(acts, now=NOW)
    assert ins.pace_trend == "insufficient-data"


# --------------------------------------------------------------------------- #
#  Dedupe (needs app context + DB)
# --------------------------------------------------------------------------- #
def test_dedupe_blocks_near_identical(app):
    from welllens.activities.parsing import ParsedActivity
    from welllens.activities.service import save_parsed_activity
    from welllens.extensions import db
    from welllens.models import User

    with app.app_context():
        user = User(name="T", email="t@example.com", username="tester")
        db.session.add(user)
        db.session.commit()

        parsed = ParsedActivity(
            start_time=datetime(2025, 6, 1, 7, 0, tzinfo=timezone.utc),
            duration_s=1800,
            distance_m=5000,
        )
        _a, created1 = save_parsed_activity(user.id, parsed)
        assert created1 is True

        # Same start (within window) + same duration -> duplicate.
        dupe = ParsedActivity(
            start_time=datetime(2025, 6, 1, 7, 0, 30, tzinfo=timezone.utc),
            duration_s=1810,
            distance_m=5010,
        )
        _b, created2 = save_parsed_activity(user.id, dupe)
        assert created2 is False


def test_dedupe_external_id(app):
    from welllens.activities.parsing import ParsedActivity
    from welllens.activities.service import save_parsed_activity
    from welllens.extensions import db
    from welllens.models import User

    with app.app_context():
        user = User(name="T2", email="t2@example.com", username="tester2")
        db.session.add(user)
        db.session.commit()

        p = ParsedActivity(
            start_time=datetime(2025, 5, 1, 8, 0, tzinfo=timezone.utc),
            duration_s=1200,
            distance_m=3000,
        )
        _a, c1 = save_parsed_activity(user.id, p, source="garmin", external_id="abc123")
        assert c1 is True

        # Different time, but same external_id -> duplicate.
        p2 = ParsedActivity(
            start_time=datetime(2025, 5, 2, 9, 0, tzinfo=timezone.utc),
            duration_s=9999,
            distance_m=1,
        )
        _b, c2 = save_parsed_activity(user.id, p2, source="garmin", external_id="abc123")
        assert c2 is False
