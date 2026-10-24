"""Small request-validation helpers shared by all modules."""
from flask import request

from app.common.errors import AppError


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AppError("invalid_json", "Request body must be a JSON object.", 400)
    return data


def required_strings(data: dict, *names: str) -> dict:
    """Return stripped values for `names`; raise 400 listing every missing/blank field."""
    values, missing = {}, {}
    for name in names:
        raw = data.get(name)
        text = raw.strip() if isinstance(raw, str) else ""
        if not text:
            missing[name] = "This field is required."
        values[name] = text
    if missing:
        raise AppError("validation_error", "Please fill in all required fields.", 400, missing)
    return values
