"""Tests for the support chatbot endpoint and escalation."""


def test_chat_escalates_without_ai(client, app):
    # TestConfig has no GROQ_API_KEY, so the bot falls back and escalates.
    r = client.post("/chat", json={"message": "Can I get a refund for last month?"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["escalated"] is True
    assert data["reply"]

    from welllens.models import SupportTicket

    with app.app_context():
        tickets = SupportTicket.query.all()
        assert len(tickets) == 1
        assert "refund" in tickets[0].question.lower()
        assert tickets[0].resolved is False


def test_chat_empty_message(client):
    r = client.post("/chat", json={"message": "   "})
    assert r.status_code == 200
    assert r.get_json()["escalated"] is False


def test_support_inbox_requires_admin(client):
    r = client.get("/admin/support", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_support_inbox_lists_and_resolves(client, app):
    # Create a ticket via the chat endpoint, then resolve it as admin.
    client.post("/chat", json={"message": "Something only a human can answer"})
    with client.session_transaction() as sess:
        sess["is_admin"] = True

    r = client.get("/admin/support")
    assert r.status_code == 200
    assert b"Something only a human" in r.data

    from welllens.models import SupportTicket

    with app.app_context():
        tid = SupportTicket.query.first().id
    client.post(f"/admin/support/{tid}/resolve", follow_redirects=True)
    with app.app_context():
        assert SupportTicket.query.get(tid).resolved is True
