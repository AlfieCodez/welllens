"""Support chatbot: answer from WellLens knowledge via Groq, escalate if unsure."""
from __future__ import annotations

import json
import logging

import requests
from flask import current_app

from .knowledge import WELLLENS_KNOWLEDGE

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_S = 15
_MAX_HISTORY = 6

_SYSTEM_PROMPT = (
    "You are WellLens's friendly support assistant. Answer the user's question using "
    "ONLY the knowledge below. Keep replies short and helpful, in plain English, no "
    "markdown.\n\n"
    "If the question is something the knowledge does NOT cover, or it's an account-"
    "specific problem, a bug, a refund/billing dispute, or anything you're unsure "
    "about, do NOT guess — set \"escalate\" to true and tell the user you'll pass it "
    "to the team.\n\n"
    'Respond ONLY as JSON: {"reply": "<your reply>", "escalate": <true|false>}.\n\n'
    "KNOWLEDGE:\n" + WELLLENS_KNOWLEDGE
)

_FALLBACK_REPLY = (
    "Thanks for your question! I can't answer that one automatically, so I've passed "
    "it to our team — they'll follow up. In the meantime: WellLens analyses your "
    "uploaded .fit/.gpx/.tcx activities into insights; Free includes 5 uploads and Pro "
    "(£4.99/month) is unlimited."
)


def answer(message: str, history: list | None = None) -> dict:
    """Return {"reply": str, "escalate": bool}."""
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me anything about WellLens!", "escalate": False}

    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key:
        # No AI available — escalate so a human can follow up.
        return {"reply": _FALLBACK_REPLY, "escalate": True}

    result = _ask_groq(message, history or [], api_key)
    if result is None:
        return {"reply": _FALLBACK_REPLY, "escalate": True}
    return result


def _ask_groq(message: str, history: list, api_key: str) -> dict | None:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for turn in history[-_MAX_HISTORY:]:
        role = turn.get("role")
        content = (turn.get("content") or "")[:1000]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message[:1500]})

    payload = {
        "model": current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "temperature": 0.3,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        reply = str(data.get("reply") or "").strip()
        escalate = bool(data.get("escalate"))
        if not reply:
            return None
        return {"reply": reply, "escalate": escalate}
    except Exception as exc:  # noqa: BLE001 — any failure -> escalate via caller
        log.warning("Chatbot Groq call failed: %s", exc)
        return None
