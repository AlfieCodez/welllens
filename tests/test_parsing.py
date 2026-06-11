"""Tests for activity file parsing."""
from pathlib import Path

import pytest

from welllens.activities.parsing import (
    ActivityParseError,
    ParsedActivity,
    parse_file,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_parse_gpx_basic():
    pa = parse_file(FIXTURES / "sample.gpx")
    assert pa.type == "running"
    assert pa.start_time.isoformat().startswith("2025-06-01T07:00:00")
    # 4 points, one minute apart -> 3 minutes.
    assert pa.duration_s == 180
    assert pa.distance_m and pa.distance_m > 0
    assert pa.avg_hr == int((120 + 140 + 160 + 150) / 4)
    assert pa.max_hr == 160
    # Elevation gain: +4 then -2 then +8 => 12 (sub-threshold noise ignored).
    assert pa.elevation_gain_m == pytest.approx(12.0, abs=0.1)
    # Pace derived from distance + duration.
    assert pa.avg_pace and pa.avg_pace > 0


def test_parse_tcx_basic():
    pa = parse_file(FIXTURES / "sample.tcx")
    assert pa.type == "running"
    assert pa.duration_s == 1800
    assert pa.distance_m == pytest.approx(5000, abs=1)
    assert pa.avg_hr is not None
    assert pa.max_hr is not None
    # 1800s over 5km => 360 s/km.
    assert pa.avg_pace == pytest.approx(360, abs=1)


def test_unsupported_extension():
    with pytest.raises(ActivityParseError):
        parse_file(FIXTURES / "nope.csv")


def test_pace_derivation_in_finalise():
    pa = ParsedActivity(
        start_time=None,
    )
    # Missing start_time should fail finalise.
    pa.distance_m = 1000
    pa.duration_s = 300
    with pytest.raises(ActivityParseError):
        pa.finalise()


def test_pace_not_overwritten_when_present():
    from datetime import datetime, timezone

    pa = ParsedActivity(
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        distance_m=1000,
        duration_s=300,
        avg_pace=240,
    )
    pa.finalise()
    assert pa.avg_pace == 240  # not recomputed
