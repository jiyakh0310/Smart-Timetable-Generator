"""Smart Timetable Management and Automated Classroom Allocation System - Flask app factory."""
from flask import Flask
from sqlalchemy import text

from app.common import db_diagnostics
from app.common.errors import register_error_handlers
from app.common.responses import failure, success
from app.config import load_config
from app.extensions import cors, db, jwt, migrate


def create_app(env: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(load_config(env))

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from app import models  # noqa: F401  (registers every table with SQLAlchemy / Alembic)

    migrate.init_app(app, db)

    register_error_handlers(app, jwt)

    from app.modules import register_blueprints

    register_blueprints(app)

    @app.get("/api/v1/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception as exc:
            # One redacted log line with the cause and what to do; the response carries only a coarse reason code (no host, user or secret).
            reason = db_diagnostics.classify(exc)
            app.logger.error("Health check: database unreachable [%s] %s | %s", reason, db_diagnostics.safe_message(exc), db_diagnostics.HINTS[reason])
            db.session.rollback()
            return failure("database_unavailable", "Database is not reachable.", 503, {"reason": reason})
        return success({"status": "ok"})

    from app.cli import register_cli

    register_cli(app)
    return app
