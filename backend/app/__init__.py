import os

from dotenv import load_dotenv
from flask import Flask

from .extensions import db, migrate


def create_app(config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", "")
    app.config["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")
    app.config["GEMINI_MODEL"] = os.environ.get("GEMINI_MODEL", "")
    app.config["ML_SERVICE_URL"] = os.environ.get("ML_SERVICE_URL", "")
    # Comma-separated Google OAuth iOS client ids accepted as the ID-token `aud` (POST /auth/oauth/google).
    app.config["GOOGLE_IOS_CLIENT_IDS"] = os.environ.get("GOOGLE_IOS_CLIENT_IDS", "")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    if config:
        app.config.update(config)

    db.init_app(app)
    migrate.init_app(app, db)

    from . import models  # noqa: F401  (register tables for Alembic)
    from .errors import register_error_handlers
    from .routes import auth, friends, groups, health, insights, items, requests, share

    register_error_handlers(app)
    for mod in (health, auth, items, share, insights, friends, groups, requests):
        app.register_blueprint(mod.bp)
    return app
