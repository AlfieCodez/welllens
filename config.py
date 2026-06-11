"""Application configuration, loaded from environment variables.

All secrets live in the environment (see .env.example). Nothing here is
hardcoded except safe-for-dev defaults.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root if present.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _split_emails(raw: str) -> set[str]:
    """Parse a comma-separated allowlist into a normalised lowercase set."""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


class Config:
    # ---- Core ----
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # ---- Paths ----
    # UPLOAD_DIR is env-overridable so production can point it at a persistent
    # volume (e.g. /data/uploads on Fly.io).
    INSTANCE_DIR = Path(os.environ.get("INSTANCE_DIR", BASE_DIR / "instance"))
    UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "uploads"))

    # ---- Database ----
    # Default: SQLite file under instance/. Set DATABASE_URL to a Postgres URL
    # (e.g. Neon) in production so data survives redeploys.
    _raw_db_url = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'welllens.db').as_posix()}"
    )
    # Some providers hand out the legacy "postgres://" scheme; SQLAlchemy needs
    # "postgresql://".
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Recycle connections so Postgres (Neon) doesn't drop idle ones under us.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # ---- Uploads ----
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    ALLOWED_EXTENSIONS = {".fit", ".gpx", ".tcx"}
    # Free-tier upload cap (manual uploads). Pro/comped/admin are unlimited.
    FREE_UPLOAD_LIMIT = int(os.environ.get("FREE_UPLOAD_LIMIT", "5"))

    # ---- Stripe (subscriptions) ----
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "").strip()  # the £4.99/mo price
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

    # ---- Groq (AI narration) ----
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

    # ---- Google OAuth ----
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

    # ---- Admin allowlist (server-enforced) ----
    ADMIN_EMAILS = _split_emails(os.environ.get("ADMIN_EMAILS", ""))

    # ---- TEMPORARY dev bypass ----
    # When "1", an admin user signing in with email/password is also granted an
    # admin session (so admin works before Google OAuth is configured). Turn this
    # OFF (the default) for any real deployment — admin should then be Google-only.
    ALLOW_PASSWORD_ADMIN = os.environ.get("ALLOW_PASSWORD_ADMIN", "0") == "1"

    # ---- Garmin Connect (Phase 2) — OAuth 2.0 PKCE ----
    # NOTE: Garmin migrated from OAuth 1.0a (retiring 31 Dec 2026) to OAuth 2.0 PKCE.
    # These are your app's OAuth2 client credentials from the Garmin Connect
    # Developer Program. (That program is currently on hold for new sign-ups.)
    GARMIN_CLIENT_ID = os.environ.get("GARMIN_CLIENT_ID", "").strip()
    GARMIN_CLIENT_SECRET = os.environ.get("GARMIN_CLIENT_SECRET", "").strip()
    # Optional explicit redirect URI (must match what you registered). If unset,
    # WellLens builds it from the request host.
    GARMIN_REDIRECT_URI = os.environ.get("GARMIN_REDIRECT_URI", "").strip()
    # Optional scope string; Garmin permissions are usually set per-app, so leave
    # blank unless your app requires it.
    GARMIN_SCOPE = os.environ.get("GARMIN_SCOPE", "").strip()
    # Shared secret embedded in the webhook URL you register with Garmin, so only
    # Garmin (configured with that URL) can reach the receiver.
    GARMIN_WEBHOOK_TOKEN = os.environ.get("GARMIN_WEBHOOK_TOKEN", "").strip()

    # Garmin OAuth2 / API endpoints.
    GARMIN_AUTH_URL = "https://apis.garmin.com/tools/oauth2/authorizeUser"
    GARMIN_TOKEN_URL = "https://diauth.garmin.com/di-oauth2-service/oauth/token"
    GARMIN_USER_ID_URL = "https://apis.garmin.com/wellness-api/rest/user/id"

    # ---- Session cookie hardening (overridden in ProductionConfig) ----
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")

    @property
    def google_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def garmin_enabled(self) -> bool:
        return bool(self.GARMIN_CLIENT_ID and self.GARMIN_CLIENT_SECRET)

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY and self.STRIPE_PRICE_ID)


class ProductionConfig(Config):
    """Hardened config for a real HTTPS deployment. Used by wsgi.py."""

    DEBUG = False
    # Cookies only over HTTPS, behind the proxy WellLens already trusts (ProxyFix).
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


def secret_key_is_weak(secret: str | None) -> bool:
    return secret in (None, "", "dev-only-insecure-key-change-me")
