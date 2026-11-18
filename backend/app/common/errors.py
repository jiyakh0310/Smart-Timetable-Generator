"""One exception type plus handlers so every error uses the same JSON envelope."""
from flask import current_app, request
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from werkzeug.exceptions import HTTPException

from app.common import db_diagnostics
from app.common.responses import failure

DB_DOWN_MESSAGE = "The database is temporarily unreachable. Please try again in a moment."


class AppError(Exception):
    """Raise anywhere in a request to return a clean, structured error."""

    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def register_error_handlers(app, jwt):
    @app.errorhandler(AppError)
    def handle_app_error(err):
        return failure(err.code, err.message, err.status, err.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        code = (err.name or "error").lower().replace(" ", "_")
        return failure(code, err.description or err.name, err.code or 500)

    @app.errorhandler(OperationalError)
    @app.errorhandler(InterfaceError)
    @app.errorhandler(PoolTimeoutError)
    def handle_database_down(err):
        """The database could not be reached or dropped the connection mid-request: a 503 the user can act on, not a mystery 500.

        The response carries only a coarse reason code; the redacted cause and the fix go to the log (one line, no traceback, no secrets)."""
        reason = db_diagnostics.classify(err)
        current_app.logger.error("Database unavailable during %s %s [%s] %s | %s", request.method, request.path, reason, db_diagnostics.safe_message(err), db_diagnostics.HINTS[reason])
        response, status = failure("database_unavailable", DB_DOWN_MESSAGE, 503, {"reason": reason, "retryable": db_diagnostics.is_retryable(reason)})
        response.headers["Retry-After"] = "5"
        return response, status

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        current_app.logger.exception("Unhandled %s during %s %s", type(err).__name__, request.method, request.path)
        return failure("server_error", "An unexpected error occurred.", 500)

    # JWT problems (missing, malformed, expired token) -> 401 in the same envelope.
    @jwt.unauthorized_loader
    def missing_token(_reason):
        return failure("unauthorized", "Authentication required.", 401)

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return failure("invalid_token", "Invalid authentication token.", 401)

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return failure("token_expired", "Your session has expired. Please sign in again.", 401)
