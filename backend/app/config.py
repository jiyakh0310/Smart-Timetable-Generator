"""Application configuration.

All secrets and database credentials come from environment variables
(loaded from the project-root `.env` file during development). Nothing
sensitive is hardcoded here.
"""
import os
import ssl
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

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


LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
# Query parameters that managed MySQL providers (Aiven, ...) put in their connection URLs. PyMySQL does not understand them.
SSL_QUERY_KEYS = ("ssl-mode", "ssl_mode", "sslmode", "ssl")


def _database_uri() -> str:
    """Full DATABASE_URL wins; otherwise build a MySQL URL from DB_* parts.

    Building from parts means passwords with special characters need no
    manual URL-encoding. A provider-style `mysql://` URL is always run
    through PyMySQL (the only MySQL driver this project installs); SQLAlchemy's
    default for plain `mysql://` is mysqlclient, which is what raises
    "No module named 'MySQLdb'".
    """
    return _database_url().render_as_string(hide_password=False)


def _database_url() -> URL:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        url = make_url(explicit)
        if url.get_backend_name() == "mysql":
            url = url.set(drivername="mysql+pymysql")
            query = {k: v for k, v in url.query.items() if k.lower() not in SSL_QUERY_KEYS}
            query.setdefault("charset", "utf8mb4")
            url = url.set(query=query)
        return url

    parts = {key: os.getenv(key, "") for key in ("DB_USER", "DB_PASSWORD", "DB_NAME")}
    missing = [key for key, value in parts.items() if not value or value.startswith(PLACEHOLDER_PREFIX)]
    if missing:
        raise RuntimeError(
            "Database settings missing or still placeholders in .env: " + ", ".join(missing)
        )
    return URL.create(
        "mysql+pymysql",
        username=parts["DB_USER"],
        password=parts["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=parts["DB_NAME"],
        query={"charset": "utf8mb4"},
    )


TLS_MODES = ("REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY")


def _url_ssl_mode() -> str | None:
    explicit = os.getenv("DATABASE_URL")
    if not explicit:
        return None
    for key, value in make_url(explicit).query.items():
        if key.lower() in SSL_QUERY_KEYS:
            return str(value)
    return None


def _normalise_mode(raw: str | None, source: str) -> str | None:
    mode = (raw or "").strip().upper().replace("-", "_")
    if mode in ("", "DISABLED", "FALSE", "0", "OFF"):
        return None
    mode = {"PREFERRED": "REQUIRED", "TRUE": "REQUIRED", "1": "REQUIRED", "ON": "REQUIRED"}.get(mode, mode)
    if mode not in TLS_MODES:
        raise RuntimeError(f"{source} must be one of {', '.join(TLS_MODES)} (got an unsupported value).")
    return mode


def _ca_material() -> tuple[str, str | None]:
    # Some dashboards store a multi-line value with literal "\n" sequences; accept both forms.
    pem = (os.getenv("DB_SSL_CA_PEM") or "").replace("\\n", "\n").strip()
    return pem, (os.getenv("DB_SSL_CA") or None)


def _tls_requested() -> bool:
    """TLS is switched on by a CA certificate, DB_SSL_MODE, or the ssl-mode parameter of a provider URL."""
    pem, cafile = _ca_material()
    return bool(pem or cafile or _normalise_mode(os.getenv("DB_SSL_MODE"), "DB_SSL_MODE") or _normalise_mode(_url_ssl_mode(), "ssl-mode in DATABASE_URL"))


def _tls_mode() -> str | None:
    """The effective TLS mode, or None when TLS is off.

    REQUIRED         encrypted, the server certificate is NOT checked
    VERIFY_CA        encrypted, the certificate chain is checked against your CA (the host name is not)
    VERIFY_IDENTITY  encrypted, the chain AND the host name are checked (the default whenever a CA is supplied)

    DB_SSL_MODE wins. A provider's ssl-mode=REQUIRED in DATABASE_URL never downgrades a supplied CA, but ssl-mode=VERIFY_CA / VERIFY_IDENTITY is honoured.
    """
    pem, cafile = _ca_material()
    have_ca = bool(pem or cafile)
    explicit = _normalise_mode(os.getenv("DB_SSL_MODE"), "DB_SSL_MODE")
    from_url = _normalise_mode(_url_ssl_mode(), "ssl-mode in DATABASE_URL")
    if explicit:
        mode = explicit
    elif from_url in ("VERIFY_CA", "VERIFY_IDENTITY"):
        mode = from_url
    elif have_ca:
        mode = "VERIFY_IDENTITY"
    else:
        mode = from_url
    if mode in ("VERIFY_CA", "VERIFY_IDENTITY") and not have_ca:
        raise RuntimeError(f"TLS mode {mode} needs the provider's CA certificate: set DB_SSL_CA_PEM (the certificate text) or DB_SSL_CA (a file path).")
    return mode


def _ssl_context() -> ssl.SSLContext | None:
    """TLS settings for the MySQL connection (read from environment variables only).

    DB_SSL_CA_PEM  the CA certificate text (Aiven: the "CA certificate" in the service overview)
    DB_SSL_CA      or a path to that certificate file (e.g. a Render Secret File)
    DB_SSL_MODE    REQUIRED | VERIFY_CA | VERIFY_IDENTITY - see `_tls_mode`
    """
    mode = _tls_mode()
    if mode is None:
        return None
    if mode == "REQUIRED":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    pem, cafile = _ca_material()
    ctx = ssl.create_default_context(cafile=cafile, cadata=pem or None)
    ctx.check_hostname = mode == "VERIFY_IDENTITY"
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT  # Python 3.13 tightened this; provider CAs often fail the strict profile
    return ctx


def _engine_options(production: bool) -> dict:
    options = {"pool_pre_ping": True, "pool_recycle": 280}  # managed MySQL closes idle connections; reconnect instead of failing
    url = _database_url()
    ctx = _ssl_context()
    if ctx is not None and url.get_backend_name() == "mysql":
        options["connect_args"] = {"ssl": ctx}
    elif production and url.get_backend_name() == "mysql" and (url.host or "") not in LOCAL_HOSTS:
        raise RuntimeError(
            "The database host is remote but no TLS is configured. Set DB_SSL_CA_PEM (recommended: the provider's CA certificate) "
            "or DB_SSL_CA, or DB_SSL_MODE=REQUIRED for an encrypted connection without certificate checks."
        )
    return options


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
        "SQLALCHEMY_ENGINE_OPTIONS": _engine_options(production=env == "production"),
        "CORS_ORIGINS": [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
    }
