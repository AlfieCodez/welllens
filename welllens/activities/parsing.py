"""Parse .fit / .gpx / .tcx files into a normalised activity dict.

Each parser returns a ParsedActivity. The math (distance, pace) is computed
here, never by the AI layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class ActivityParseError(Exception):
    """Raised when a file can't be parsed into a usable activity."""


@dataclass
class ParsedActivity:
    type: str | None = None
    start_time: datetime | None = None
    duration_s: int = 0
    distance_m: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_pace: float | None = None  # seconds per km
    elevation_gain_m: float | None = None
    external_id: str | None = None
    extras: dict = field(default_factory=dict)

    def finalise(self) -> "ParsedActivity":
        """Derive pace from distance+duration if not already set."""
        if self.start_time is None:
            raise ActivityParseError("Could not find a start time in this file.")
        if self.start_time.tzinfo is None:
            self.start_time = self.start_time.replace(tzinfo=timezone.utc)
        if (
            self.avg_pace is None
            and self.distance_m
            and self.distance_m > 0
            and self.duration_s
        ):
            self.avg_pace = self.duration_s / (self.distance_m / 1000)
        return self


def parse_file(path: str | Path) -> ParsedActivity:
    """Dispatch to the right parser based on file extension."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".fit":
        return parse_fit(path).finalise()
    if ext == ".gpx":
        return parse_gpx(path).finalise()
    if ext == ".tcx":
        return parse_tcx(path).finalise()
    raise ActivityParseError(f"Unsupported file type: {ext or 'unknown'}")


# --------------------------------------------------------------------------- #
#  .FIT
# --------------------------------------------------------------------------- #
def parse_fit(path: Path) -> ParsedActivity:
    from fitparse import FitFile

    try:
        fit = FitFile(str(path))
        fit.parse()
    except Exception as exc:  # noqa: BLE001
        raise ActivityParseError("This .fit file looks corrupted or unreadable.") from exc

    pa = ParsedActivity()
    # Prefer the 'session' message which summarises the whole activity.
    for msg in fit.get_messages("session"):
        d = {f.name: f.value for f in msg}
        pa.type = _norm_sport(d.get("sport"))
        pa.start_time = d.get("start_time")
        pa.duration_s = int(d.get("total_timer_time") or d.get("total_elapsed_time") or 0)
        pa.distance_m = _to_float(d.get("total_distance"))
        pa.avg_hr = _to_int(d.get("avg_heart_rate"))
        pa.max_hr = _to_int(d.get("max_heart_rate"))
        pa.elevation_gain_m = _to_float(d.get("total_ascent"))
        break

    # Fall back to scanning records if no session summary present.
    if pa.start_time is None:
        pa = _fit_from_records(fit, pa)

    if pa.start_time is None:
        raise ActivityParseError("No activity data found in this .fit file.")
    return pa


def _fit_from_records(fit, pa: ParsedActivity) -> ParsedActivity:
    times, hrs, dists, alts = [], [], [], []
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg}
        if d.get("timestamp"):
            times.append(d["timestamp"])
        if d.get("heart_rate") is not None:
            hrs.append(d["heart_rate"])
        if d.get("distance") is not None:
            dists.append(d["distance"])
        if d.get("altitude") is not None:
            alts.append(d["altitude"])
    if times:
        pa.start_time = times[0]
        pa.duration_s = int((times[-1] - times[0]).total_seconds())
    if dists:
        pa.distance_m = _to_float(dists[-1])
    if hrs:
        pa.avg_hr = int(sum(hrs) / len(hrs))
        pa.max_hr = max(hrs)
    if alts:
        pa.elevation_gain_m = _ascent(alts)
    return pa


# --------------------------------------------------------------------------- #
#  .GPX
# --------------------------------------------------------------------------- #
def parse_gpx(path: Path) -> ParsedActivity:
    import gpxpy

    try:
        with open(path, "r", encoding="utf-8") as fh:
            gpx = gpxpy.parse(fh)
    except Exception as exc:  # noqa: BLE001
        raise ActivityParseError("This .gpx file couldn't be read as valid GPX.") from exc

    pa = ParsedActivity()
    times, hrs, alts = [], [], []
    total_distance = 0.0

    for track in gpx.tracks:
        pa.type = pa.type or _norm_sport(track.type)
        for segment in track.segments:
            total_distance += segment.length_3d() or 0.0
            for pt in segment.points:
                if pt.time:
                    times.append(pt.time)
                if pt.elevation is not None:
                    alts.append(pt.elevation)
                hr = _gpx_hr(pt)
                if hr is not None:
                    hrs.append(hr)

    if not times:
        raise ActivityParseError("This .gpx file has no timestamped track points.")

    times.sort()
    pa.start_time = times[0]
    pa.duration_s = int((times[-1] - times[0]).total_seconds())
    pa.distance_m = round(total_distance, 1) if total_distance else None
    if hrs:
        pa.avg_hr = int(sum(hrs) / len(hrs))
        pa.max_hr = max(hrs)
    if alts:
        pa.elevation_gain_m = _ascent(alts)
    return pa


def _gpx_hr(point) -> int | None:
    """Pull heart rate from GPX TrackPointExtension if present."""
    for ext in getattr(point, "extensions", []) or []:
        for child in ext.iter():
            tag = child.tag.split("}")[-1].lower()
            if tag in ("hr", "heartrate") and child.text:
                try:
                    return int(float(child.text))
                except ValueError:
                    return None
    return None


# --------------------------------------------------------------------------- #
#  .TCX
# --------------------------------------------------------------------------- #
def parse_tcx(path: Path) -> ParsedActivity:
    from tcxparser import TCXParser

    try:
        tcx = TCXParser(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ActivityParseError("This .tcx file couldn't be read as valid TCX.") from exc

    pa = ParsedActivity()
    try:
        pa.start_time = _parse_iso(tcx.started_at)
    except Exception as exc:  # noqa: BLE001
        raise ActivityParseError("No start time found in this .tcx file.") from exc

    pa.type = _norm_sport(getattr(tcx, "activity_type", None))
    pa.duration_s = int(tcx.duration or 0)
    pa.distance_m = _to_float(tcx.distance)
    pa.avg_hr = _to_int(getattr(tcx, "hr_avg", None))
    pa.max_hr = _to_int(getattr(tcx, "hr_max", None))
    pa.elevation_gain_m = _to_float(getattr(tcx, "ascent", None))
    return pa


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _ascent(altitudes: list[float], threshold: float = 0.5) -> float:
    """Sum positive elevation changes, ignoring sub-threshold GPS noise."""
    gain = 0.0
    for prev, cur in zip(altitudes, altitudes[1:]):
        delta = cur - prev
        if delta > threshold:
            gain += delta
    return round(gain, 1)


def _norm_sport(value) -> str | None:
    if not value:
        return None
    return str(value).replace("_", " ").strip().lower()


def _to_float(value) -> float | None:
    try:
        f = float(value)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
