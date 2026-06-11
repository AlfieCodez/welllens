"""Compute wellbeing metrics from stored activities.

Everything numerical happens here. The AI layer only narrates these results.
All times are treated as UTC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def activity_load(duration_s: int | None, avg_hr: int | None) -> float:
    """A simple session load: minutes, scaled by heart-rate intensity if known.

    Without HR we fall back to raw minutes so every activity still counts.
    """
    minutes = (duration_s or 0) / 60.0
    if avg_hr and avg_hr > 0:
        # Scale around a ~140bpm reference so easy/hard sessions differ.
        return minutes * (avg_hr / 140.0)
    return minutes


@dataclass
class WeekBucket:
    week_start: datetime  # Monday 00:00 UTC
    distance_m: float = 0.0
    duration_s: int = 0
    load: float = 0.0
    count: int = 0

    @property
    def distance_km(self) -> float:
        return round(self.distance_m / 1000, 2)


@dataclass
class Insights:
    total_activities: int = 0
    acwr: float | None = None
    acwr_flag: str = "unknown"  # low | balanced | watch | high | unknown
    acute_load: float = 0.0
    chronic_load: float = 0.0
    weekly: list[WeekBucket] = field(default_factory=list)
    this_week_km: float = 0.0
    last_week_km: float = 0.0
    wow_distance_pct: float | None = None
    pace_trend: str = "insufficient-data"  # improving | steady | declining
    pace_trend_detail: str | None = None

    def to_summary_dict(self) -> dict:
        """Compact, AI-friendly view of the numbers (no objects)."""
        return {
            "total_activities": self.total_activities,
            "acwr": round(self.acwr, 2) if self.acwr is not None else None,
            "acwr_flag": self.acwr_flag,
            "this_week_km": round(self.this_week_km, 1),
            "last_week_km": round(self.last_week_km, 1),
            "wow_distance_pct": (
                round(self.wow_distance_pct, 1)
                if self.wow_distance_pct is not None
                else None
            ),
            "pace_trend": self.pace_trend,
            "pace_trend_detail": self.pace_trend_detail,
        }


def _week_start(dt: datetime) -> datetime:
    dt = _as_utc(dt)
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def compute_insights(activities, now: datetime | None = None) -> Insights:
    """Compute all metrics from an iterable of Activity-like objects.

    Each item needs: start_time, duration_s, distance_m, avg_hr, avg_pace.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    acts = sorted(activities, key=lambda a: _as_utc(a.start_time))
    ins = Insights(total_activities=len(acts))
    if not acts:
        return ins

    _compute_weekly(acts, ins, now)
    _compute_acwr(acts, ins, now)
    _compute_pace_trend(acts, ins)
    return ins


def _compute_weekly(acts, ins: Insights, now: datetime) -> None:
    buckets: dict[datetime, WeekBucket] = {}
    for a in acts:
        ws = _week_start(a.start_time)
        b = buckets.setdefault(ws, WeekBucket(week_start=ws))
        b.distance_m += a.distance_m or 0
        b.duration_s += a.duration_s or 0
        b.load += activity_load(a.duration_s, a.avg_hr)
        b.count += 1

    ins.weekly = [buckets[k] for k in sorted(buckets)]

    this_ws = _week_start(now)
    last_ws = this_ws - timedelta(days=7)
    this_week = buckets.get(this_ws)
    last_week = buckets.get(last_ws)
    ins.this_week_km = this_week.distance_km if this_week else 0.0
    ins.last_week_km = last_week.distance_km if last_week else 0.0
    if last_week and last_week.distance_m > 0:
        ins.wow_distance_pct = (
            (ins.this_week_km - ins.last_week_km) / last_week.distance_km * 100
        )


def _compute_acwr(acts, ins: Insights, now: datetime) -> None:
    """ACWR = last 7 days' load vs the average weekly load over 28 days."""
    acute_cut = now - timedelta(days=7)
    chronic_cut = now - timedelta(days=28)

    acute = sum(
        activity_load(a.duration_s, a.avg_hr)
        for a in acts
        if _as_utc(a.start_time) >= acute_cut
    )
    chronic_total = sum(
        activity_load(a.duration_s, a.avg_hr)
        for a in acts
        if _as_utc(a.start_time) >= chronic_cut
    )
    chronic = chronic_total / 4.0  # average per week over 4 weeks

    ins.acute_load = round(acute, 1)
    ins.chronic_load = round(chronic, 1)

    if chronic <= 0:
        ins.acwr = None
        ins.acwr_flag = "unknown"
        return

    ratio = acute / chronic
    ins.acwr = ratio
    ins.acwr_flag = _acwr_flag(ratio)


def _acwr_flag(ratio: float) -> str:
    if ratio < 0.8:
        return "low"
    if ratio <= 1.3:
        return "balanced"
    if ratio <= 1.5:
        return "watch"
    return "high"


def _compute_pace_trend(acts, ins: Insights) -> None:
    """Is pace at a given HR improving? Compare HR-normalised pace over time.

    Lower seconds/km at the same HR = improving fitness. We compare the
    earlier half of sessions to the later half.
    """
    points = [
        (a.avg_pace / a.avg_hr)
        for a in acts
        if a.avg_pace and a.avg_hr and a.avg_hr > 0
    ]
    if len(points) < 4:
        ins.pace_trend = "insufficient-data"
        return

    mid = len(points) // 2
    early = sum(points[:mid]) / mid
    late = sum(points[mid:]) / (len(points) - mid)
    if early == 0:
        ins.pace_trend = "insufficient-data"
        return

    change = (late - early) / early * 100  # negative = faster at same HR
    if change <= -3:
        ins.pace_trend = "improving"
    elif change >= 3:
        ins.pace_trend = "declining"
    else:
        ins.pace_trend = "steady"
    ins.pace_trend_detail = (
        f"HR-adjusted pace changed {change:+.1f}% from your earlier to recent sessions."
    )
