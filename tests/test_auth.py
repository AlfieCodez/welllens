"""Integration tests for the auth flow (CSRF disabled in TestConfig)."""


def test_register_login_and_dashboard(client):
    # Register.
    resp = client.post(
        "/register",
        data={
            "name": "Alex Carter",
            "email": "alex@example.com",
            "username": "alexc",
            "password": "supersecret",
            "confirm": "supersecret",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Logged in -> dashboard greets them.
    assert b"Hello, Alex" in resp.data

    # Logout, then bad login.
    client.get("/logout")
    bad = client.post(
        "/login", data={"email": "alex@example.com", "password": "wrong"}
    )
    assert bad.status_code == 401
    assert b"Incorrect email or password" in bad.data

    # Good login.
    good = client.post(
        "/login",
        data={"email": "alex@example.com", "password": "supersecret"},
        follow_redirects=True,
    )
    assert b"Hello, Alex" in good.data


def test_register_rejects_short_password(client):
    resp = client.post(
        "/register",
        data={
            "name": "Bo",
            "email": "bo@example.com",
            "username": "bo123",
            "password": "short",
            "confirm": "short",
        },
    )
    assert resp.status_code == 400
    assert b"at least 8 characters" in resp.data


def test_register_rejects_duplicate_email(client):
    data = {
        "name": "One",
        "email": "dup@example.com",
        "username": "userone",
        "password": "supersecret",
        "confirm": "supersecret",
    }
    client.post("/register", data=data, follow_redirects=True)
    client.get("/logout")
    data2 = dict(data, username="usertwo")
    resp = client.post("/register", data=data2)
    assert resp.status_code == 400
    assert b"already exists" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_requires_admin_session(client):
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
