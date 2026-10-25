"""Why the database is unreachable: reason codes, redaction, the health endpoint, TLS modes and the db-check command.

The deployed health check answered only "database_unavailable" in about a second, which means the host was reachable and the connection
was then rejected (TLS verification, credentials or database name). These tests pin each of those causes to its own reason code.
"""
import datetime
import ipaddress
import logging
import socket
import ssl
import threading

import pymysql
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.exc import OperationalError

from app import config, create_app
from app.common import db_diagnostics as dx
from app.extensions import db

ENV_KEYS = ("DATABASE_URL", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT", "DB_SSL_CA_PEM", "DB_SSL_CA", "DB_SSL_MODE")
PASSWORD = "Sup3r-Secret-Pw"


def wrapped(*args, cls=pymysql.err.OperationalError):
    """What SQLAlchemy raises: its own OperationalError wrapping the driver's."""
    return OperationalError("SELECT 1", {}, cls(*args))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)


class TestClassification:
    @pytest.mark.parametrize("exc,reason", [
        (wrapped(1045, "Access denied for user 'avnadmin'@'10.0.0.1' (using password: YES)"), "authentication_failed"),
        (wrapped(1044, "Access denied for user 'avnadmin'@'%' to database 'smart_timetable_m1'"), "database_access_denied"),
        (wrapped(1049, "Unknown database 'smart_timetable_m1'"), "unknown_database"),
        (wrapped(3159, "Connections using insecure transport are prohibited while --require_secure_transport=ON."), "tls_required"),
        (wrapped(1129, "Host '10.1.1.1' is blocked because of many connection errors"), "host_not_allowed"),
        (wrapped(1130, "Host '10.1.1.1' is not allowed to connect to this MySQL server"), "host_not_allowed"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' (timed out)"), "network_timeout"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([Errno -2] Name or service not known)"), "dns_failure"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([Errno 111] Connection refused)"), "connection_refused"),
        (wrapped(2013, "Lost connection to MySQL server during query"), "connection_failed"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'h'. (_ssl.c:1020))"), "tls_hostname_mismatch"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: IP address mismatch, certificate is not valid for '1.2.3.4'.)"), "tls_hostname_mismatch"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1020))"), "tls_certificate_untrusted"),
        (wrapped(2003, "Can't connect to MySQL server on 'h' ([SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1020))"), "tls_handshake_failed"),
        (RuntimeError("something nobody has seen before"), "unknown"),
    ])
    def test_each_cause_gets_its_own_reason(self, exc, reason):
        assert dx.classify(exc) == reason

    def test_a_real_certificate_error_chained_under_the_driver_error_is_recognised(self):
        try:
            try:
                raise ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'x'.")
            except ssl.SSLCertVerificationError as inner:
                raise pymysql.err.OperationalError(2003, "Can't connect to MySQL server on 'x'") from inner
        except pymysql.err.OperationalError as exc:
            assert dx.classify(OperationalError("SELECT 1", {}, exc)) == "tls_hostname_mismatch"

    def test_every_reason_has_advice(self):
        for reason in ("tls_hostname_mismatch", "tls_certificate_untrusted", "tls_handshake_failed", "tls_required", "authentication_failed", "database_access_denied",
                       "unknown_database", "host_not_allowed", "network_timeout", "dns_failure", "connection_refused", "connection_failed", "unknown"):
            assert dx.HINTS[reason]
        assert "VERIFY_CA" in dx.HINTS["tls_hostname_mismatch"]


class TestRedaction:
    def test_passwords_and_url_passwords_never_appear(self, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", PASSWORD)
        monkeypatch.setenv("DATABASE_URL", f"mysql://avnadmin:{PASSWORD}@h:1/db")
        exc = wrapped(2003, f"cannot use mysql://avnadmin:{PASSWORD}@h:1/db because {PASSWORD} is wrong")
        line = dx.safe_message(exc)
        assert PASSWORD not in line and "***" in line

    def test_a_url_password_is_hidden_even_when_unknown_to_the_environment(self):
        assert "hunter22" not in dx.redact("failed for mysql://user:hunter22@host/db")

    def test_secret_keys_and_the_ca_text_are_hidden(self, monkeypatch):
        monkeypatch.setenv("DB_SSL_CA_PEM", "-----BEGIN CERTIFICATE-----ABCDEF-----END CERTIFICATE-----")
        assert "ABCDEF" not in dx.redact("bad ca -----BEGIN CERTIFICATE-----ABCDEF-----END CERTIFICATE-----")
        assert ("a" * 40) not in dx.redact("key " + "a" * 40)

    def test_the_message_is_one_bounded_line_with_the_error_types(self):
        line = dx.safe_message(wrapped(1049, "Unknown\ndatabase 'x'" + " pad" * 300))
        assert "\n" not in line and len(line) <= 400 and line.startswith("OperationalError")


class TestHealthEndpoint:
    @pytest.fixture()
    def client(self):
        app = create_app("testing")
        with app.app_context():
            db.create_all()
            yield app.test_client()
            db.session.remove()
            db.drop_all()

    def test_healthy(self, client):
        assert client.get("/api/v1/health").get_json()["data"] == {"status": "ok"}

    def test_failure_gives_a_reason_code_but_no_internals(self, client, monkeypatch, caplog):
        monkeypatch.setenv("DB_PASSWORD", PASSWORD)
        boom = wrapped(1045, f"Access denied for user 'avnadmin'@'10.0.0.1' (using password: YES) {PASSWORD}")
        monkeypatch.setattr(db.session, "execute", lambda *a, **k: (_ for _ in ()).throw(boom))
        with caplog.at_level(logging.ERROR):
            response = client.get("/api/v1/health")
        body = response.get_json()
        assert response.status_code == 503 and body["success"] is False
        assert body["error"] == {"code": "database_unavailable", "message": "Database is not reachable.", "details": {"reason": "authentication_failed"}}
        text = response.get_data(as_text=True)
        assert PASSWORD not in text and "avnadmin" not in text and "10.0.0.1" not in text

    def test_the_log_line_names_the_cause_and_the_fix_without_the_secret(self, client, monkeypatch, caplog):
        monkeypatch.setenv("DB_PASSWORD", PASSWORD)
        boom = wrapped(1049, f"Unknown database 'smart_timetable_m1' {PASSWORD}")
        monkeypatch.setattr(db.session, "execute", lambda *a, **k: (_ for _ in ()).throw(boom))
        with caplog.at_level(logging.ERROR):
            client.get("/api/v1/health")
        lines = [r.getMessage() for r in caplog.records if "Health check" in r.getMessage()]
        assert len(lines) == 1
        assert "[unknown_database]" in lines[0] and "smart_timetable_m1" in lines[0] and "database name" in lines[0].lower()
        assert PASSWORD not in lines[0]

    def test_the_session_is_usable_again_after_a_failure(self, client, monkeypatch):
        real = db.session.execute
        monkeypatch.setattr(db.session, "execute", lambda *a, **k: (_ for _ in ()).throw(wrapped(2003, "timed out")))
        assert client.get("/api/v1/health").get_json()["error"]["details"]["reason"] == "network_timeout"
        monkeypatch.setattr(db.session, "execute", real)
        assert client.get("/api/v1/health").status_code == 200


# ---------- TLS modes ----------
@pytest.fixture(scope="module")
def pki():
    """A CA, and a server certificate for 'other.example.com' only (so connecting to 'db.example.com' is a host name mismatch)."""
    def make_key():
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key, srv_key = make_key(), make_key()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    srv = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "other.example.com")])).issuer_name(ca_name)
           .public_key(srv_key.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName("other.example.com")]), critical=False).sign(ca_key, hashes.SHA256()))
    pem = lambda obj: obj.public_bytes(serialization.Encoding.PEM)
    key_pem = srv_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
    return {"ca": pem(ca).decode(), "cert": pem(srv), "key": key_pem}


def handshake(client_ctx, pki, tmp_path, hostname="db.example.com"):
    """A real TLS handshake between our client context and a server presenting the certificate above. Returns None, or the error."""
    cert, key = tmp_path / "srv.crt", tmp_path / "srv.key"
    cert.write_bytes(pki["cert"])
    key.write_bytes(pki["key"])
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(cert, key)
    a, b = socket.socketpair()
    result = {}

    def serve():
        try:
            with server_ctx.wrap_socket(b, server_side=True) as s:
                s.recv(1)
        except Exception as exc:  # the client may hang up on a rejected certificate
            result["server"] = exc

    t = threading.Thread(target=serve)
    t.start()
    try:
        with client_ctx.wrap_socket(a, server_hostname=hostname) as c:
            c.send(b"x")
        return None
    except ssl.SSLError as exc:
        return exc
    finally:
        t.join(timeout=5)


class TestTlsModes:
    def env(self, monkeypatch, pki, mode=None, url="mysql://u:p@db.example.com:3306/app?ssl-mode=REQUIRED"):
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("DB_SSL_CA_PEM", pki["ca"])
        if mode:
            monkeypatch.setenv("DB_SSL_MODE", mode)

    def test_with_a_ca_the_default_checks_the_host_name_too(self, monkeypatch, pki, tmp_path):
        self.env(monkeypatch, pki)
        assert config._tls_mode() == "VERIFY_IDENTITY"
        err = handshake(config._ssl_context(), pki, tmp_path)
        assert isinstance(err, ssl.SSLCertVerificationError) and dx.classify(err) == "tls_hostname_mismatch"

    def test_verify_ca_accepts_a_certificate_for_another_host_name_but_still_checks_the_chain(self, monkeypatch, pki, tmp_path):
        self.env(monkeypatch, pki, "VERIFY_CA")
        ctx = config._ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is False
        assert handshake(ctx, pki, tmp_path) is None
        # a certificate NOT signed by our CA is still rejected
        other = ssl.create_default_context(cadata=_other_ca())
        other.check_hostname = False
        assert isinstance(handshake(other, pki, tmp_path), ssl.SSLCertVerificationError)

    def test_verify_identity_passes_when_the_host_name_matches(self, monkeypatch, pki, tmp_path):
        self.env(monkeypatch, pki, "VERIFY_IDENTITY")
        assert handshake(config._ssl_context(), pki, tmp_path, hostname="other.example.com") is None

    def test_required_encrypts_without_checking_anything(self, monkeypatch, tmp_path, pki):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@db.example.com/app?ssl-mode=REQUIRED")
        assert config._tls_mode() == "REQUIRED"
        assert handshake(config._ssl_context(), pki, tmp_path) is None

    def test_the_urls_ssl_mode_required_never_downgrades_a_supplied_ca(self, monkeypatch, pki):
        self.env(monkeypatch, pki)                                     # URL says REQUIRED, a CA is present
        assert config._tls_mode() == "VERIFY_IDENTITY"

    def test_the_urls_verify_modes_are_honoured(self, monkeypatch, pki):
        self.env(monkeypatch, pki, url="mysql://u:p@h/app?ssl-mode=VERIFY_CA")
        assert config._tls_mode() == "VERIFY_CA"

    def test_an_explicit_db_ssl_mode_wins_over_the_url(self, monkeypatch, pki):
        self.env(monkeypatch, pki, "VERIFY_CA", url="mysql://u:p@h/app?ssl-mode=VERIFY_IDENTITY")
        assert config._tls_mode() == "VERIFY_CA"

    @pytest.mark.parametrize("mode", ["VERIFY_CA", "VERIFY_IDENTITY"])
    def test_a_verifying_mode_without_a_ca_is_refused_with_advice(self, monkeypatch, mode):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/app")
        monkeypatch.setenv("DB_SSL_MODE", mode)
        with pytest.raises(RuntimeError) as err:
            config._ssl_context()
        assert "DB_SSL_CA_PEM" in str(err.value)

    def test_an_unknown_mode_is_refused(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/app")
        monkeypatch.setenv("DB_SSL_MODE", "sometimes")
        with pytest.raises(RuntimeError) as err:
            config._ssl_context()
        assert "REQUIRED" in str(err.value)

    @pytest.mark.parametrize("raw,expected", [("verify-ca", "VERIFY_CA"), ("Verify_Identity", "VERIFY_IDENTITY"), ("required", "REQUIRED"), ("PREFERRED", "REQUIRED")])
    def test_the_spelling_of_the_mode_is_forgiving(self, monkeypatch, pki, raw, expected):
        self.env(monkeypatch, pki, raw)
        assert config._tls_mode() == expected

    @pytest.mark.parametrize("raw", ["DISABLED", "off", "false", ""])
    def test_disabled_values_switch_tls_off_when_there_is_no_ca(self, monkeypatch, raw):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@127.0.0.1/app")
        monkeypatch.setenv("DB_SSL_MODE", raw)
        assert config._ssl_context() is None


def _other_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Somebody Else")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class TestDbCheckCommand:
    def run(self, app):
        return app.test_cli_runner().invoke(args=["db-check"])

    def test_reports_success_for_a_reachable_database(self):
        app = create_app("testing")
        with app.app_context():
            db.create_all()
        # the SQLite test database has no SHOW STATUS; the command must still end with a clear failure rather than a crash
        result = self.run(app)
        assert "driver=sqlite" in result.output and "TLS: off" in result.output
        assert "SELECT 1: 1" in result.output

    def test_reports_the_reason_and_advice_and_no_password_on_failure(self, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", PASSWORD)
        app = create_app("testing")
        boom = wrapped(1045, f"Access denied for user 'u'@'h' (using password: YES) {PASSWORD}")
        with app.app_context():
            monkeypatch.setattr(db.engine, "connect", lambda *a, **k: (_ for _ in ()).throw(boom))
            result = self.run(app)
        assert result.exit_code == 1
        assert "FAILED [authentication_failed]" in result.output and "What to change:" in result.output and PASSWORD not in result.output
