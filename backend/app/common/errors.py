"""One exception type plus handlers so every error uses the same JSON envelope."""
from flask import current_app
from werkzeug.exceptions import HTTPException

from app.common.responses import failure


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

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        current_app.logger.exception("Unhandled error")
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
