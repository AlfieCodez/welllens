"""Google OAuth client registration (Authlib)."""
from flask import Flask

from ..extensions import oauth

_GOOGLE_NAME = "google"


def register_google(app: Flask) -> None:
    """Register the Google OIDC client if credentials are configured."""
    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    if not (client_id and client_secret):
        return  # Google sign-in stays disabled; email/password still works.

    oauth.register(
        name=_GOOGLE_NAME,
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=app.config["GOOGLE_DISCOVERY_URL"],
        client_kwargs={"scope": "openid email profile"},
    )


def google_enabled() -> bool:
    return _GOOGLE_NAME in {c for c in getattr(oauth, "_clients", {})}
