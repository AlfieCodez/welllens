"""Seed development accounts so you can log in without registering.

Run from the project root:
    py scripts/seed_dev.py

Creates (idempotently):
  - a normal demo user
  - an admin user (whose email is also added to ADMIN_EMAILS for Google later)

TEMPORARY dev convenience. Delete these accounts before any real deployment.
"""
import sys
from pathlib import Path

# Make the project root importable.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from welllens import create_app  # noqa: E402
from welllens.extensions import db  # noqa: E402
from welllens.models import User  # noqa: E402

# ---- edit these if you like ----
DEMO_EMAIL = "demo@welllens.local"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "welllens123"

ADMIN_EMAIL = "alfiehen2012@outlook.com"  # admin allowlist email
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "welllens123"


def upsert_user(name, email, username, password, is_admin=False):
    user = User.query.filter_by(email=email.lower()).first()
    created = user is None
    if user is None:
        user = User(name=name, email=email.lower(), username=username)
        db.session.add(user)
    user.is_admin = is_admin
    user.set_password(password)
    db.session.commit()
    return user, created


def main():
    app = create_app()
    with app.app_context():
        _u, demo_new = upsert_user(
            "Demo User", DEMO_EMAIL, DEMO_USERNAME, DEMO_PASSWORD, is_admin=False
        )
        _a, admin_new = upsert_user(
            "Admin", ADMIN_EMAIL, ADMIN_USERNAME, ADMIN_PASSWORD, is_admin=True
        )

    print("\n  WellLens dev accounts ready")
    print("  " + "-" * 40)
    print(f"  Demo user   {'(created)' if demo_new else '(updated)'}")
    print(f"    email:    {DEMO_EMAIL}")
    print(f"    password: {DEMO_PASSWORD}")
    print(f"\n  Admin user  {'(created)' if admin_new else '(updated)'}")
    print(f"    email:    {ADMIN_EMAIL}")
    print(f"    password: {ADMIN_PASSWORD}")
    print("  " + "-" * 40)
    print("  Admin via password needs ALLOW_PASSWORD_ADMIN=1 in .env.\n")


if __name__ == "__main__":
    main()
