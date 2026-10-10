import os

from dotenv import load_dotenv
from flask import Flask

from .extensions import db, migrate


def create_app(config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
    app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", "")
    if config:
        app.config.update(config)

    db.init_app(app)
    migrate.init_app(app, db)

    from .routes.health import bp as health_bp

    app.register_blueprint(health_bp)
    return app
