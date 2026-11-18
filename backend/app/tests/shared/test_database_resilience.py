"""Intermittent database outages: retry/recovery, a clear 503 instead of a mystery 500, safe login diagnostics, liveness vs readiness."""
import logging
import socket

import pymysql
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError

from app import config, create_app
from app.common import db_diagnostics as dx
from app.common import db_resilience
from app.extensions import db
from app.seed import demo_password, seed_demo_data


def op_error(code, message):
    return OperationalError("connect", {}, pymysql.err.OperationalError(code, message))


DNS_NOT_FOUND = lambda: op_error(2003, "Can't connect to MySQL server on 'h' ([Errno -2] Name or service not known)")
DNS_TEMPORARY = lambda: op_error(2003, "Can't connect to MySQL server on 'h' ([Errno -3] Temporary failure in name resolution)")
AUTH_FAILED = lambda: op_error(1045, "Access denied for user 'u'@'h' (using password: YES)")


class FlakyConnect:
    """Stands in for `dialect.connect`: raises the given errors one after another, then hands out a real SQLite connection."""

    def __init__(self, engine, errors):
        self.errors, self.calls, self.real = list(errors), 0, engine.dialect.connect
        engine.dialect.connect = self

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)()
        return self.real(*args, **kwargs)


def engine_with(errors, attempts=3, delay=0.5):
    pauses = []
    engine = create_engine("sqlite://")
    flaky = FlakyConnect(engine, errors)
    db_resilience.install(engine, attempts, delay, sleep=pauses.append)
    return engine, flaky, pauses


class TestRetry:
    def test_a_transient_dns_failure_is_retried_and_the_request_succeeds(self):
        engine, flaky, pauses = engine_with([DNS_TEMPORARY, DNS_NOT_FOUND])
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT 1").scalar() == 1
        assert flaky.calls == 3 and pauses == [0.5, 1.0]        # growing pause: delay * attempt

    def test_the_error_is_raised_when_every_attempt_fails(self):
        engine, flaky, pauses = engine_with([DNS_TEMPORARY] * 5)
        with pytest.raises(OperationalError) as err:
            engine.connect()
        assert dx.classify(err.value) == "dns_temporary" and flaky.calls == 3 and len(pauses) == 2

    @pytest.mark.parametrize("bad", [AUTH_FAILED, lambda: op_error(1049, "Unknown database 'x'"),
                                     lambda: op_error(2003, "([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch)")])
    def test_permanent_problems_are_never_retried(self, bad):
        engine, flaky, pauses = engine_with([bad, bad, bad])
        with pytest.raises(OperationalError):
            engine.connect()
        assert flaky.calls == 1 and pauses == []

    def test_one_attempt_means_no_retry_hook_at_all(self):
        engine, flaky, pauses = engine_with([DNS_TEMPORARY], attempts=1)
        with pytest.raises(OperationalError):
            engine.connect()
        assert flaky.calls == 1 and pauses == []

    def test_each_retry_and_the_final_failure_are_logged_with_the_reason_and_no_secret(self, caplog, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "Sup3r-Secret-Pw")
        engine, _, _ = engine_with([lambda: op_error(2003, "Can't connect to 'h' ([Errno -3] Temporary failure in name resolution) Sup3r-Secret-Pw")] * 3)
        with caplog.at_level(logging.WARNING, logger="app.db"):
            with pytest.raises(OperationalError):
                engine.connect()
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "attempt 1/3 failed [dns_temporary]" in text and "attempt 2/3" in text and "failed after 3 attempts [dns_temporary]" in text
        assert "Sup3r-Secret-Pw" not in text

    def test_which_reasons_can_clear_by_themselves(self):
        assert all(dx.is_retryable(r) for r in ("dns_not_found", "dns_temporary", "network_timeout", "connection_refused", "connection_failed"))
        assert not any(dx.is_retryable(r) for r in ("authentication_failed", "unknown_database", "database_access_denied", "tls_hostname_mismatch",
                                                    "tls_certificate_untrusted", "tls_required", "host_not_allowed", "unknown"))


class TestSettings:
    def test_defaults(self):
        assert db_resilience.settings() == {"attempts": 3, "delay": 0.5, "connect_timeout": 10, "read_timeout": 30}

    def test_values_are_clamped_to_safe_limits(self, monkeypatch):
        monkeypatch.setenv("DB_CONNECT_ATTEMPTS", "99")
        monkeypatch.setenv("DB_CONNECT_RETRY_DELAY", "-4")
        monkeypatch.setenv("DB_CONNECT_TIMEOUT", "0")
        s = db_resilience.settings()
        assert (s["attempts"], s["delay"], s["connect_timeout"]) == (6, 0, 1)

    def test_a_non_number_is_refused_by_name(self, monkeypatch):
        monkeypatch.setenv("DB_CONNECT_ATTEMPTS", "many")
        with pytest.raises(RuntimeError) as err:
            db_resilience.settings()
        assert "DB_CONNECT_ATTEMPTS" in str(err.value)

    def test_the_mysql_engine_gets_bounded_waits_and_hidden_sql_parameters(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@127.0.0.1:3306/app")
        monkeypatch.setenv("DB_CONNECT_TIMEOUT", "7")
        options = config._engine_options(production=False)
        assert options["connect_args"]["connect_timeout"] == 7 and options["connect_args"]["read_timeout"] == 30
        assert options["hide_parameters"] is True and options["pool_pre_ping"] is True


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        seed_demo_data()
        yield app
        db.session.remove()
        db.drop_all()


def break_database(monkeypatch, error):
    def boom(*args, **kwargs):
        raise error()
    monkeypatch.setattr(db.session, "scalar", boom)
    monkeypatch.setattr(db.session, "execute", boom)


class TestLoginDuringAnOutage:
    LOGIN = {"email": "admin@timetable.test", "password": "whatever-it-is"}

    def test_a_database_outage_is_a_503_with_a_reason_not_a_mystery_500(self, app, monkeypatch):
        break_database(monkeypatch, DNS_TEMPORARY)
        r = app.test_client().post("/api/v1/auth/login", json=self.LOGIN)
        body = r.get_json()
        assert r.status_code == 503 and r.headers["Retry-After"] == "5"
        assert body["error"]["code"] == "database_unavailable" and "try again" in body["error"]["message"].lower()
        assert body["error"]["details"] == {"reason": "dns_temporary", "retryable": True}

    def test_a_permanent_cause_is_reported_as_not_retryable(self, app, monkeypatch):
        break_database(monkeypatch, AUTH_FAILED)
        body = app.test_client().post("/api/v1/auth/login", json=self.LOGIN).get_json()
        assert body["error"]["details"] == {"reason": "authentication_failed", "retryable": False}

    def test_the_response_never_contains_connection_details_or_the_users_email(self, app, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "Sup3r-Secret-Pw")
        break_database(monkeypatch, lambda: op_error(2003, "Can't connect to MySQL server on 'secret-host.example.com' Sup3r-Secret-Pw"))
        text = app.test_client().post("/api/v1/auth/login", json=self.LOGIN).get_data(as_text=True)
        assert "secret-host" not in text and "Sup3r-Secret-Pw" not in text and "admin@timetable.test" not in text

    def test_the_log_line_names_the_request_the_cause_and_the_fix_without_secrets(self, app, monkeypatch, caplog):
        monkeypatch.setenv("DB_PASSWORD", "Sup3r-Secret-Pw")
        break_database(monkeypatch, lambda: op_error(2003, "Can't connect to MySQL server on 'h' ([Errno -2] Name or service not known) Sup3r-Secret-Pw"))
        with caplog.at_level(logging.ERROR):
            app.test_client().post("/api/v1/auth/login", json=self.LOGIN)
        line = next(r.getMessage() for r in caplog.records if "Database unavailable" in r.getMessage())
        assert "POST /api/v1/auth/login" in line and "[dns_not_found]" in line and "host name" in line.lower()
        assert "Sup3r-Secret-Pw" not in line and "admin@timetable.test" not in line

    def test_other_database_endpoints_get_the_same_clear_answer(self, app, monkeypatch):
        token = app.test_client().post("/api/v1/auth/login", json={"email": "admin@timetable.test", "password": demo_password()}).get_json()["data"]["token"]
        break_database(monkeypatch, DNS_TEMPORARY)
        r = app.test_client().get("/api/v1/rooms", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code in (503, 401) and r.get_json()["error"]["code"] in ("database_unavailable", "unauthorized")

    def test_ordinary_failures_are_unchanged(self, app, monkeypatch):
        client = app.test_client()
        assert client.post("/api/v1/auth/login", json={"email": "admin@timetable.test", "password": "wrong-password"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={}).status_code == 400
        ok = client.post("/api/v1/auth/login", json={"email": "admin@timetable.test", "password": demo_password()})
        assert ok.status_code == 200 and ok.get_json()["data"]["token"]

    def test_a_bug_or_integrity_error_is_still_a_500_not_a_database_outage(self, app, monkeypatch):
        monkeypatch.setattr(db.session, "scalar", lambda *a, **k: (_ for _ in ()).throw(IntegrityError("x", {}, Exception("dup"))))
        r = app.test_client().post("/api/v1/auth/login", json=self.LOGIN)
        assert r.status_code == 500 and r.get_json()["error"]["code"] == "server_error"

    def test_the_unexpected_error_log_names_the_request(self, app, monkeypatch, caplog):
        monkeypatch.setattr(db.session, "scalar", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
        with caplog.at_level(logging.ERROR):
            app.test_client().post("/api/v1/auth/login", json=self.LOGIN)
        assert any("Unhandled ValueError during POST /api/v1/auth/login" in r.getMessage() for r in caplog.records)


class TestLoginLogging:
    def post(self, app, email, password):
        return app.test_client().post("/api/v1/auth/login", json={"email": email, "password": password})

    def test_each_rejection_reason_is_logged_but_never_the_email_or_password(self, app, caplog):
        from app.models import User
        db.session.scalar(db.select(User).filter_by(email="faculty2@timetable.test")).is_active = False
        db.session.commit()
        with caplog.at_level(logging.INFO):
            self.post(app, "nobody@example.com", "pw-123456")
            self.post(app, "admin@timetable.test", "WrongPassword-9")
            self.post(app, "faculty2@timetable.test", demo_password())
        text = "\n".join(r.getMessage() for r in caplog.records)
        for reason in ("unknown_email", "wrong_password", "account_disabled"):
            assert f"Login rejected [{reason}]" in text
        for secret in ("nobody@example.com", "admin@timetable.test", "WrongPassword-9", "pw-123456", demo_password()):
            assert secret not in text

    def test_a_success_logs_only_the_user_id_and_role(self, app, caplog):
        with caplog.at_level(logging.INFO):
            assert self.post(app, "admin@timetable.test", demo_password()).status_code == 200
        line = next(r.getMessage() for r in caplog.records if "Login ok" in r.getMessage())
        assert "role=admin" in line and "user_id=" in line and "admin@timetable.test" not in line

    def test_the_client_still_gets_one_generic_message_for_every_rejection(self, app):
        messages = {self.post(app, e, p).get_json()["error"]["message"] for e, p in (("nobody@example.com", "x" * 9), ("admin@timetable.test", "Wrong-Pass-1"))}
        assert messages == {"Invalid email or password."}


class TestHealthEndpoints:
    def test_liveness_never_touches_the_database(self, app, monkeypatch):
        break_database(monkeypatch, DNS_TEMPORARY)
        r = app.test_client().get("/api/v1/health/live")
        assert r.status_code == 200 and r.get_json()["data"] == {"status": "alive"}

    def test_readiness_reports_the_reason_and_whether_retrying_can_help(self, app, monkeypatch):
        break_database(monkeypatch, DNS_TEMPORARY)
        error = app.test_client().get("/api/v1/health").get_json()["error"]
        assert error["details"] == {"reason": "dns_temporary", "retryable": True}

    def test_readiness_recovers_when_the_database_comes_back(self, app, monkeypatch):
        real = db.session.execute
        monkeypatch.setattr(db.session, "execute", lambda *a, **k: (_ for _ in ()).throw(DNS_TEMPORARY()))
        assert app.test_client().get("/api/v1/health").status_code == 503
        monkeypatch.setattr(db.session, "execute", real)
        assert app.test_client().get("/api/v1/health").get_json()["data"] == {"status": "ok"}


class TestDbCheckDns:
    def test_the_command_checks_dns_first_and_explains_a_missing_host(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@missing-host.example.test:3306/app?ssl-mode=REQUIRED")
        monkeypatch.setenv("DB_CONNECT_ATTEMPTS", "1")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)

        def no_dns(*args, **kwargs):
            raise socket.gaierror(-2, "Name or service not known")
        monkeypatch.setattr(socket, "getaddrinfo", no_dns)
        app = create_app("production")
        result = app.test_cli_runner().invoke(args=["db-check"])
        assert result.exit_code == 1
        assert "DNS: FAILED for missing-host.example.test [dns_not_found]" in result.output
        assert "FAILED [dns_not_found]" in result.output and "powered-off" in result.output
        assert "p@" not in result.output and ":p@" not in result.output

    def test_it_reports_how_many_addresses_resolved(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@db.example.test:3306/app?ssl-mode=REQUIRED")
        monkeypatch.setenv("DB_CONNECT_ATTEMPTS", "1")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)
        real = socket.getaddrinfo
        monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("10.0.0.7", 3306))] if host == "db.example.test" else real(host, *a, **k))
        result = create_app("production").test_cli_runner().invoke(args=["db-check"])
        assert "DNS: db.example.test resolves to 1 address(es)" in result.output


class TestRealUnresolvableHost:
    """No mocks: the production configuration pointed at a host that cannot exist (RFC 6761 reserves .invalid), through the real PyMySQL driver."""

    @pytest.fixture()
    def prod_client(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@no-such-host-zz.invalid:3306/app?ssl-mode=REQUIRED")
        monkeypatch.setenv("DB_CONNECT_ATTEMPTS", "2")
        monkeypatch.setenv("DB_CONNECT_RETRY_DELAY", "0")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)
        return create_app("production").test_client()

    def test_login_is_a_clear_503_and_the_connection_was_retried(self, prod_client, caplog):
        with caplog.at_level(logging.WARNING):
            r = prod_client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x" * 9})
        assert r.status_code == 503
        details = r.get_json()["error"]["details"]
        assert details["reason"] in ("dns_not_found", "dns_temporary") and details["retryable"] is True
        retried = [x.getMessage() for x in caplog.records if "attempt 1/2 failed" in x.getMessage()]
        assert retried and "no-such-host-zz" in retried[0]        # the host is in the server log, never in the response
        assert "no-such-host-zz" not in r.get_data(as_text=True)

    def test_the_web_process_stays_alive_and_readiness_says_why(self, prod_client):
        assert prod_client.get("/api/v1/health/live").status_code == 200
        r = prod_client.get("/api/v1/health")
        assert r.status_code == 503 and r.get_json()["error"]["details"]["reason"] in ("dns_not_found", "dns_temporary")
