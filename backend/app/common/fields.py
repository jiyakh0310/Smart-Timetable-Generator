"""Small field-validation helpers for service modules. Each records a message in `errors` and returns None on failure."""
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def whole_number(value, field: str, errors: dict, lo: int, hi: int):
    """An int in [lo, hi]. Booleans, floats and numeric strings are rejected."""
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = "Must be a whole number."
        return None
    if not lo <= value <= hi:
        errors[field] = f"Must be between {lo} and {hi}."
        return None
    return value


def text(value, field: str, errors: dict, min_len: int, max_len: int, label: str | None = None):
    """Trimmed text with inner whitespace collapsed, length-checked."""
    if not isinstance(value, str):
        errors[field] = "Must be text."
        return None
    cleaned = " ".join(value.split())
    if not min_len <= len(cleaned) <= max_len:
        errors[field] = f"{label or 'This field'} must be {min_len} to {max_len} characters." if min_len > 1 else f"Enter up to {max_len} characters."
        return None
    return cleaned


def optional_text(value, field: str, errors: dict, max_len: int):
    """Optional text: None, '' or whitespace-only -> None; otherwise trimmed, whitespace collapsed, length-checked."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return text(value, field, errors, 1, max_len)


def email(value, field: str, errors: dict):
    """Optional email: None/'' -> None; otherwise a lower-cased address of at most 255 characters."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        errors[field] = "Must be text."
        return None
    cleaned = value.strip().lower()
    if len(cleaned) > 255 or not EMAIL_RE.match(cleaned):
        errors[field] = "Enter a valid email address, e.g. name@college.edu."
        return None
    return cleaned


def reject_unknown(data: dict, allowed: set[str], error_cls):
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise error_cls("validation_error", f"Unknown field(s): {', '.join(unknown)}.", 400, {u: "Not allowed." for u in unknown})
