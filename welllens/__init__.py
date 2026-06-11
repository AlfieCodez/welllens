"""WellLens application factory."""
from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, secret_key_is_weak
from .extensions import csrf, db, oauth


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Respect X-Forwarded-* from a TLS-terminating proxy (cloudflared, nginx,
    # the host platform) so _external URLs use https and the right host.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Warn (don't crash) if a public deployment is running with a weak secret.
    if not app.config.get("DEBUG") and secret_key_is_weak(app.config.get("SECRET_KEY")):
        app.logger.warning(
            "SECRET_KEY is not set to a strong value. Set it before exposing this "
            "app publicly — sessions can be forged otherwise."
        )

    # Ensure runtime dirs exist.
    config_class.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    config_class.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Init extensions.
    db.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)

    # Register the Google OAuth client (no-op if creds missing).
    from .auth.google import register_google
    register_google(app)

    # Blueprints.
    from .main.routes import main_bp
    from .auth.routes import auth_bp
    from .activities.routes import activities_bp
    from .dashboard.routes import dashboard_bp
    from .garmin.routes import garmin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(activities_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(garmin_bp)

    # Expose Garmin availability to templates (read straight from config — never
    # instantiate the config class per request).
    @app.context_processor
    def inject_flags():
        return {
            "garmin_enabled": bool(
                app.config.get("GARMIN_CLIENT_ID")
                and app.config.get("GARMIN_CLIENT_SECRET")
            )
        }

    # Create tables on first run.
    with app.app_context():
        from . import models  # noqa: F401  (ensure models are imported)
        db.create_all()

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(RequestEntityTooLarge)
    def too_large(e):  # noqa: ANN001
        mb = app.config["MAX_UPLOAD_MB"]
        return (
            render_template(
                "error.html",
                code=413,
                message=f"That file is too large. The limit is {mb} MB.",
            ),
            413,
        )

    @app.errorhandler(404)
    def not_found(e):  # noqa: ANN001
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(500)
    def server_error(e):  # noqa: ANN001
        return (
            render_template(
                "error.html", code=500, message="Something went wrong on our end."
            ),
            500,
        )
