"""Turn computed metrics into a short, friendly summary.

Primary path: Groq's free API. If no key is set, or the call fails for any
reason, fall back to a deterministic plain-text template so WellLens always
produces useful text with zero AI dependency.
"""
from __future__ import annotations

import logging

import requests
from flask import current_app

from .compute import Insights

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_S = 12

_ACWR_WORDS = {
    "low": "Your recent training load is light compared with your usual — a good "
    "window to build back up gradually.",
    "balanced": "Your training load is well balanced against your recent average — "
    "a sustainable place to be.",
    "watch": "Your load has crept above your recent average. Worth keeping an eye "
    "on recovery this week.",
    "high": "Your recent load is well above your 4-week average, which raises "
    "overtraining risk. Consider an easier few days.",
    "unknown": "Log a few more activities and WellLens can assess your training "
    "load balance.",
}

_PACE_WORDS = {
    "improving": "Encouragingly, your pace at a given heart rate is improving — a "
    "classic sign of rising fitness.",
    "steady": "Your pace at a given heart rate is holding steady.",
    "declining": "Your pace at a given heart rate has slipped a little lately, which "
    "can follow heavy load or fatigue.",
    "insufficient-data": "",
}


def narrate(ins: Insights) -> str:
    """Return insight text, preferring Groq and falling back to a template."""
    text = _try_groq(ins)
    if text:
        return text
    return plain_summary(ins)


def plain_summary(ins: Insights) -> str:
    """Deterministic, no-AI summary built from the numbers."""
    if ins.total_activities == 0:
        return (
            "No activities yet — upload your first .fit, .gpx or .tcx file and "
            "WellLens will start finding patterns in your training."
        )

    parts: list[str] = []
    parts.append(
        f"You've logged {ins.total_activities} "
        f"{'activity' if ins.total_activities == 1 else 'activities'} so far."
    )

    if ins.this_week_km or ins.last_week_km:
        line = f"This week you've covered {ins.this_week_km:.1f} km"
        if ins.wow_distance_pct is not None:
            direction = "up" if ins.wow_distance_pct >= 0 else "down"
            line += (
                f", {direction} {abs(ins.wow_distance_pct):.0f}% on last week's "
                f"{ins.last_week_km:.1f} km."
            )
        else:
            line += "."
        parts.append(line)

    parts.append(_ACWR_WORDS.get(ins.acwr_flag, ""))
    if ins.acwr is not None:
        parts.append(f"(ACWR {ins.acwr:.2f}.)")

    pace = _PACE_WORDS.get(ins.pace_trend, "")
    if pace:
        parts.append(pace)

    return " ".join(p for p in parts if p).strip()


def _try_groq(ins: Insights) -> str | None:
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key:
        return None  # No key -> template fallback.

    model = current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    payload = {
        "model": model,
        "temperature": 0.5,
        "max_tokens": 220,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(ins)},
        ],
    }
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text or None
    except Exception as exc:  # noqa: BLE001  — any failure falls back gracefully
        log.warning("Groq narration failed, using template fallback: %s", exc)
        return None


_SYSTEM_PROMPT = (
    "You are WellLens, a calm, encouraging wellbeing coach. You are given "
    "pre-computed training metrics as JSON. Write 2-4 short sentences of plain-"
    "English insight for the athlete. Be warm and concrete. Do NOT invent numbers "
    "beyond those given, do not give medical advice, and do not use markdown."
)


def _user_prompt(ins: Insights) -> str:
    import json

    return (
        "Here are my computed metrics. Summarise what they mean for my training "
        "and recovery:\n" + json.dumps(ins.to_summary_dict(), indent=2)
    )
