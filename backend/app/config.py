"""Application configuration.

All secrets and database credentials come from environment variables
(loaded from the project-root `.env` file during development). Nothing
sensitive is hardcoded here.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

# backend/app/config.py -> project root is two levels above `app/`
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

PLACEHOLDER_PREFIX = "replace-with"
MIN_SECRET_LENGTH = 32


def _require_secret(name: str) -> str:
    value = os.getenv(name, "")
    if not value or value.startswith(PLACEHOLDER_PREFIX) or len(value) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"{name} is missing, still a placeholder, or shorter than {MIN_SECRET_LENGTH} characters. "
            "Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\"  "
            "and put it in your .env file."
        )
    return value


def _database_uri() -> str:
    """Full DATABASE_URL wins; otherwise build a MySQL URL from DB_* parts.

    Building from parts means passwords with special characters need no
    manual URL-encoding.
    """
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit

    parts = {key: os.getenv(key, "") for key in ("DB_USER", "DB_PASSWORD", "DB_NAME")}
    missing = [key for key, value in parts.items() if not value or value.startswith(PLACEHOLDER_PREFIX)]
    if missing:
        raise RuntimeError(
            "Database settings missing or still placeholders in .env: " + ", ".join(missing)
        )
    url = URL.create(
        "mysql+pymysql",
        username=parts["DB_USER"],
        password=parts["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=parts["DB_NAME"],
        query={"charset": "utf8mb4"},
    )
    return url.render_as_string(hide_password=False)


def load_config(env: str | None = None) -> dict:
    env = env or os.getenv("APP_ENV", "development")

    if env == "testing":
        # Fixed keys are fine here: the testing database is a throwaway in-memory SQLite.
        return {
            "APP_ENV": env,
            "TESTING": True,
            "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",  # fast hashing for tests only; real configs use scrypt
            "SECRET_KEY": "testing-only-secret-key-0000000000000000",
            "JWT_SECRET_KEY": "testing-only-jwt-secret-key-00000000000",
            "JWT_ACCESS_TOKEN_EXPIRES": timedelta(minutes=30),
            "SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:"),
            "CORS_ORIGINS": ["http://localhost:5173"],
        }

    if env not in ("development", "production"):
        raise RuntimeError(f"Unknown APP_ENV '{env}'. Use development, production or testing.")

    return {
        "APP_ENV": env,
        "DEBUG": env == "development",
        "SECRET_KEY": _require_secret("SECRET_KEY"),
        "JWT_SECRET_KEY": _require_secret("JWT_SECRET_KEY"),
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "8"))),
        "SQLALCHEMY_DATABASE_URI": _database_uri(),
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "CORS_ORIGINS": [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    }
