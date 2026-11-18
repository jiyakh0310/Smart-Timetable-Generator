"""Recovery from short database outages (DNS hiccups, timeouts, a node restarting).

A connection that fails for a reason that can clear by itself (see `db_diagnostics.RETRYABLE`) is retried a few times with a growing
pause before the error reaches the request. Permanent problems (wrong password, TLS verification, unknown database) fail at once.
Nothing is hidden: every retry and the final failure are logged with the redacted reason.

Settings (environment variables, all optional):
  DB_CONNECT_ATTEMPTS       total tries per new connection, 1-6        (default 3; 1 turns retrying off)
  DB_CONNECT_RETRY_DELAY    seconds before retry n is  delay * n, 0-5  (default 0.5)
  DB_CONNECT_TIMEOUT        seconds to wait for the TCP/TLS connect    (default 10)
  DB_READ_TIMEOUT           seconds to wait for a query result         (default 30)
"""
import logging
import os
import time

from sqlalchemy import event

from app.common import db_diagnostics

log = logging.getLogger("app.db")


def _number(name: str, default: float, low: float, high: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else default
    except ValueError:
        raise RuntimeError(f"{name} must be a number.") from None
    return min(max(value, low), high)


def settings() -> dict:
    return {
        "attempts": int(_number("DB_CONNECT_ATTEMPTS", 3, 1, 6)),
        "delay": _number("DB_CONNECT_RETRY_DELAY", 0.5, 0, 5),
        "connect_timeout": int(_number("DB_CONNECT_TIMEOUT", 10, 1, 60)),
        "read_timeout": int(_number("DB_READ_TIMEOUT", 30, 1, 300)),
    }


def install(engine, attempts: int, delay: float, sleep=time.sleep) -> None:
    """Make every NEW connection of `engine` retry transient connect failures. Pooled connections are untouched (pre-ping handles those)."""
    if attempts <= 1:
        return

    @event.listens_for(engine, "do_connect")
    def connect_with_retry(dialect, conn_rec, cargs, cparams):
        host = cparams.get("host") or "?"   # a host name is not a secret; it belongs in the server log (never in a response)
        for attempt in range(1, attempts + 1):
            try:
                return dialect.connect(*cargs, **cparams)
            except Exception as exc:  # noqa: BLE001 - classified below; anything that cannot clear by itself is re-raised untouched
                reason = db_diagnostics.classify(exc)
                if not db_diagnostics.is_retryable(reason) or attempt == attempts:
                    if attempt > 1:
                        log.error("Database connection failed after %d attempts [%s] host=%s | %s", attempt, reason, host, db_diagnostics.safe_message(exc))
                    raise
                pause = delay * attempt
                log.warning("Database connection attempt %d/%d failed [%s] host=%s; retrying in %.1fs | %s", attempt, attempts, reason, host, pause, db_diagnostics.safe_message(exc))
                sleep(pause)
        raise AssertionError("unreachable")  # pragma: no cover
