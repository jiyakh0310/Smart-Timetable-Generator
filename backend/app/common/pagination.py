"""Query-string helpers shared by every list endpoint (page, per_page, filters)."""
from flask import request

from app.common.errors import AppError
from app.extensions import db


def int_arg(name: str, default=None, minimum: int | None = None, maximum: int | None = None):
    """Read an optional integer query parameter; 400 with a field message if it is invalid."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise AppError("validation_error", f"'{name}' must be a whole number.", 400, {name: "Must be a whole number."}) from None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        bounds = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise AppError("validation_error", f"'{name}' must be {bounds}.", 400, {name: f"Must be {bounds}."})
    return value


def bool_arg(name: str):
    """'true' / 'false' -> bool, missing -> None, anything else -> 400."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    raise AppError("validation_error", f"'{name}' must be true or false.", 400, {name: "Must be true or false."})


def pagination_args(default_per_page: int = 20, max_per_page: int = 100) -> tuple[int, int]:
    return int_arg("page", 1, minimum=1), int_arg("per_page", default_per_page, minimum=1, maximum=max_per_page)


def paginate(statement, page: int, per_page: int, serialize) -> dict:
    """Run a SELECT with LIMIT/OFFSET. `serialize` receives the list of rows on this page."""
    result = db.paginate(statement, page=page, per_page=per_page, error_out=False, count=True)
    return {
        "items": serialize(result.items),
        "page": page,
        "per_page": per_page,
        "total": result.total,
        "pages": max(result.pages, 1),
    }
