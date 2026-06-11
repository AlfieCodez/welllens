"""Chatbot endpoint + admin support inbox."""
import logging

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from ..auth.helpers import admin_required, current_user
from ..extensions import csrf, db
from ..models import SupportTicket
from . import service

log = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)

_MAX_MESSAGE_LEN = 1500


@chat_bp.route("/chat", methods=["POST"])
@csrf.exempt  # JSON endpoint; available to logged-out visitors too.
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()[:_MAX_MESSAGE_LEN]
    history = data.get("history") if isinstance(data.get("history"), list) else []
    if not message:
        return jsonify({"reply": "Ask me anything about WellLens!", "escalated": False})

    result = service.answer(message, history)

    escalated = bool(result.get("escalate"))
    if escalated:
        _create_ticket(message, result.get("reply"))

    return jsonify({"reply": result.get("reply", ""), "escalated": escalated})


def _create_ticket(question: str, bot_reply: str | None) -> None:
    user = current_user()
    ticket = SupportTicket(
        user_id=user.id if user else None,
        email=user.email if user else None,
        question=question,
        bot_reply=bot_reply,
    )
    db.session.add(ticket)
    db.session.commit()
    log.info("Support ticket #%s created", ticket.id)


# --------------------------------------------------------------------------- #
#  Admin support inbox
# --------------------------------------------------------------------------- #
@chat_bp.route("/admin/support")
@admin_required
def inbox():
    tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
    return render_template(
        "support_inbox.html",
        user=current_user(),
        tickets=tickets,
        open_count=sum(1 for t in tickets if not t.resolved),
    )


@chat_bp.route("/admin/support/<int:ticket_id>/resolve", methods=["POST"])
@admin_required
def resolve(ticket_id):
    ticket = db.session.get(SupportTicket, ticket_id)
    if ticket:
        ticket.resolved = not ticket.resolved
        db.session.commit()
        flash(
            f"Ticket #{ticket.id} marked {'resolved' if ticket.resolved else 'open'}.",
            "success",
        )
    return redirect(url_for("chat.inbox"))
