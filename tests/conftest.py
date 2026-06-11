"""Shared pytest fixtures."""
import sys
from pathlib import Path

import pytest

# Make the project root importable when running `pytest` from anywhere.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from welllens import create_app  # noqa: E402
from welllens.extensions import db  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-key"
    GROQ_API_KEY = ""  # force template fallback in tests


@pytest.fixture
def app():
    app = create_app(TestConfig)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def client_app(app):
    """Return (app, test_client) for tests that also tweak app.config."""
    return app, app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session
