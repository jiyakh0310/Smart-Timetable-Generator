"""Turns a database connection failure into a short, safe reason.

The health endpoint used to answer only "database_unavailable". The cause (wrong password, wrong database name, a TLS certificate
that does not match, a blocked network...) is what you actually need, but the raw error text can contain host names and user names,
so it is only written to the server log (after redaction). The browser / health response gets just the coarse reason code below.
"""
import os
import re
import ssl

# reason code -> what to do about it (also printed by `flask --app run db-check`)
HINTS = {
    "tls_hostname_mismatch": "The server certificate is valid but not issued for this host name. Set DB_SSL_MODE=VERIFY_CA (chain is still verified against your CA).",
    "tls_certificate_untrusted": "The server certificate is not signed by the CA you supplied. Re-copy the CA certificate from the provider's service page into DB_SSL_CA_PEM.",
    "tls_handshake_failed": "TLS could not be negotiated. Check the port, that the database requires/offers TLS, and DB_SSL_CA_PEM / DB_SSL_MODE.",
    "tls_required": "The server only accepts TLS. Set DB_SSL_CA_PEM (recommended) or DB_SSL_MODE=REQUIRED.",
    "authentication_failed": "The database user name or password is wrong. Check DATABASE_URL (or DB_USER / DB_PASSWORD); URL-encode special characters in the password.",
    "database_access_denied": "The user is not allowed to use this database. Check the database name and the user's privileges.",
    "unknown_database": "The database name does not exist on this server. Check the name at the end of DATABASE_URL (or DB_NAME).",
    "host_not_allowed": "The server refuses connections from this address. Check the provider's IP allow-list.",
    "network_timeout": "The connection timed out. Check host and port, and the provider's IP allow-list / firewall.",
    "dns_failure": "The host name cannot be resolved. Check the host in DATABASE_URL (or DB_HOST).",
    "connection_refused": "Nothing is listening on that host and port. Check the port in DATABASE_URL (or DB_PORT).",
    "connection_failed": "The server could not be reached or dropped the connection. Check host, port, TLS settings and the provider's status.",
    "unknown": "Unclassified error; see the redacted message in the log.",
}

URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+(@)")


def _chain(exc: BaseException) -> list[BaseException]:
    """The exception plus everything it wraps (SQLAlchemy `orig`, `__cause__`, `__context__`)."""
    seen, out, stack = set(), [], [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        out.append(e)
        stack += [getattr(e, "orig", None), e.__cause__, e.__context__]
    return out


def _errno(chain: list[BaseException]) -> int | None:
    for e in chain:
        if e.args and isinstance(e.args[0], int):
            return e.args[0]
    return None


def classify(exc: BaseException) -> str:
    chain = _chain(exc)
    text = " | ".join(str(e) for e in chain).lower()
    code = _errno(chain)
    if any(isinstance(e, ssl.SSLCertVerificationError) for e in chain) or "certificate verify failed" in text:
        return "tls_hostname_mismatch" if ("hostname mismatch" in text or "ip address mismatch" in text) else "tls_certificate_untrusted"
    if any(isinstance(e, ssl.SSLError) for e in chain) or "ssl" in text and ("handshake" in text or "wrong version" in text or "unsupported protocol" in text):
        return "tls_handshake_failed"
    if code == 3159 or "secure transport" in text or "require_secure_transport" in text:
        return "tls_required"
    if code == 1045 or "access denied for user" in text and "to database" not in text:
        return "authentication_failed"
    if code == 1044 or "access denied for user" in text:
        return "database_access_denied"
    if code == 1049 or "unknown database" in text:
        return "unknown_database"
    if code in (1129, 1130) or "is not allowed to connect" in text or "is blocked because of many connection errors" in text:
        return "host_not_allowed"
    if "timed out" in text or "timeout" in text:
        return "network_timeout"
    if any(p in text for p in ("name or service not known", "getaddrinfo", "nodename nor servname", "temporary failure in name resolution", "no address associated")):
        return "dns_failure"
    if "connection refused" in text or "winerror 10061" in text:
        return "connection_refused"
    if code in (2002, 2003, 2006, 2013) or "can't connect" in text or "lost connection" in text or "server has gone away" in text:
        return "connection_failed"
    return "unknown"


def _secrets() -> list[str]:
    values = [os.getenv(k, "") for k in ("DB_PASSWORD", "SECRET_KEY", "JWT_SECRET_KEY", "DB_SSL_CA_PEM")]
    url = os.getenv("DATABASE_URL")
    if url:
        try:
            from sqlalchemy.engine import make_url
            values.append(make_url(url).password or "")
        except Exception:  # an unparsable URL has nothing we could usefully redact
            pass
    return sorted({v for v in values if v and len(v) >= 4}, key=len, reverse=True)


def redact(text: str) -> str:
    for secret in _secrets():
        text = text.replace(secret, "***")
    return URL_PASSWORD.sub(r"\1***\2", text)


def safe_message(exc: BaseException, limit: int = 400) -> str:
    """One redacted line: the exception types and the innermost message, never a password, URL password or certificate."""
    chain = _chain(exc)
    root = next((e for e in reversed(chain) if not hasattr(e, "orig")), exc)
    types = " > ".join(dict.fromkeys(type(e).__name__ for e in chain[:4]))
    line = f"{types}: {root}".replace("\n", " ")
    return redact(line)[:limit]
