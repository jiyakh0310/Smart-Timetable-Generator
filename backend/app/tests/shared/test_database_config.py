"""Database URL and TLS configuration (Render + Aiven MySQL).

The production failure was `No module named 'MySQLdb'`: a provider URL starting with `mysql://` made SQLAlchemy pick mysqlclient.
Everything here is pure configuration: nothing connects to a database.
"""
import datetime
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine

from app import config

ENV_KEYS = ("DATABASE_URL", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT", "DB_SSL_CA_PEM", "DB_SSL_CA", "DB_SSL_MODE", "APP_ENV")
SECRET = "p@ss/word:#1"          # a deliberately awkward password
AIVEN = "mysql://avnadmin:p%40ss%2Fword%3A%231@mysql-demo.a.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("JWT_SECRET_KEY", "b" * 40)


@pytest.fixture(scope="module")
def ca_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Project CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class TestDriver:
    def test_a_provider_mysql_url_is_run_through_pymysql(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        url = config._database_url()
        assert url.drivername == "mysql+pymysql"
        assert (url.host, url.port, url.database, url.username) == ("mysql-demo.a.aivencloud.com", 12345, "defaultdb", "avnadmin")
        assert url.password == SECRET                       # URL-encoded characters survive
        assert url.query == {"charset": "utf8mb4"}          # ssl-mode removed (PyMySQL would reject it), charset added

    @pytest.mark.parametrize("scheme", ["mysql", "mysql+mysqldb", "mysql+pymysql", "mysql+mysqlconnector"])
    def test_every_mysql_scheme_ends_up_on_pymysql(self, monkeypatch, scheme):
        monkeypatch.setenv("DATABASE_URL", f"{scheme}://u:p@db.example.com:3306/app")
        assert config._database_url().drivername == "mysql+pymysql"

    def test_the_resulting_url_resolves_to_pymysql_without_mysqldb(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        engine = create_engine(config._database_uri())      # creates the dialect; does not connect
        assert engine.dialect.driver == "pymysql"

    def test_the_url_string_never_loses_the_password_encoding(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        assert create_engine(config._database_uri()).url.password == SECRET

    def test_a_charset_already_in_the_url_is_kept(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db?charset=utf8")
        assert config._database_url().query["charset"] == "utf8"

    def test_the_separate_settings_still_work_and_need_no_url_encoding(self, monkeypatch):
        for k, v in {"DB_USER": "u", "DB_PASSWORD": SECRET, "DB_NAME": "app", "DB_HOST": "db.example.com", "DB_PORT": "3307"}.items():
            monkeypatch.setenv(k, v)
        url = config._database_url()
        assert (url.drivername, url.host, url.port, url.password) == ("mysql+pymysql", "db.example.com", 3307, SECRET)

    def test_other_databases_are_left_alone(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
        assert str(config._database_url()) == "sqlite:///local.db"
        assert config._ssl_context() is None

    def test_missing_settings_are_reported_by_name_without_values(self):
        with pytest.raises(RuntimeError) as err:
            config._database_url()
        assert "DB_USER" in str(err.value)


class TestTls:
    def test_ssl_mode_in_the_url_means_encrypted_without_certificate_checks(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        ctx = config._ssl_context()
        assert ctx.verify_mode == ssl.CERT_NONE and ctx.check_hostname is False

    def test_a_ca_certificate_gives_full_verification(self, monkeypatch, ca_pem):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem)
        ctx = config._ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
        assert len(ctx.get_ca_certs()) == 1                 # only the provider CA is trusted, not the whole system store

    def test_a_ca_pasted_with_literal_backslash_n_is_accepted(self, monkeypatch, ca_pem):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem.strip().replace("\n", "\\n"))
        assert config._ssl_context().verify_mode == ssl.CERT_REQUIRED

    def test_a_ca_file_path_works(self, monkeypatch, ca_pem, tmp_path):
        path = tmp_path / "ca.pem"
        path.write_text(ca_pem)
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA", str(path))
        ctx = config._ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True

    def test_a_broken_certificate_stops_the_app_instead_of_silently_skipping_verification(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", "-----BEGIN CERTIFICATE-----\nnot a certificate\n-----END CERTIFICATE-----")
        with pytest.raises(ssl.SSLError):
            config._ssl_context()

    def test_the_ca_alone_switches_tls_on_for_the_separate_settings(self, monkeypatch, ca_pem):
        for k, v in {"DB_USER": "u", "DB_PASSWORD": "p", "DB_NAME": "app", "DB_HOST": "db.example.com"}.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem)
        assert config._ssl_context().verify_mode == ssl.CERT_REQUIRED

    def test_db_ssl_mode_alone_gives_an_encrypted_but_unverified_connection(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
        monkeypatch.setenv("DB_SSL_MODE", "REQUIRED")
        assert config._ssl_context().verify_mode == ssl.CERT_NONE

    def test_ssl_mode_disabled_in_the_url_does_not_switch_tls_on(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db?ssl-mode=DISABLED")
        assert config._ssl_context() is None

    def test_no_tls_settings_means_no_tls_for_a_local_database(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@127.0.0.1/db")
        assert config._ssl_context() is None
        assert "connect_args" not in config._engine_options(production=False)


class TestEngineOptions:
    def test_tls_reaches_the_connection_and_idle_connections_are_recycled(self, monkeypatch, ca_pem):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem)
        options = config._engine_options(production=True)
        assert isinstance(options["connect_args"]["ssl"], ssl.SSLContext)
        assert options["pool_pre_ping"] is True and options["pool_recycle"] < 300

    def test_production_refuses_a_remote_database_without_tls(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:topsecret@db.example.com:3306/app")
        with pytest.raises(RuntimeError) as err:
            config._engine_options(production=True)
        assert "DB_SSL_CA_PEM" in str(err.value) and "topsecret" not in str(err.value)

    def test_development_does_not_force_tls(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@db.example.com:3306/app")
        assert "connect_args" not in config._engine_options(production=False)

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
    def test_production_on_the_same_machine_needs_no_tls(self, monkeypatch, host):
        monkeypatch.setenv("DATABASE_URL", f"mysql://u:p@{host}:3306/app")
        assert "connect_args" not in config._engine_options(production=True)

    def test_production_accepts_a_remote_database_with_tls(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)      # ssl-mode=REQUIRED is enough to avoid the refusal
        assert "ssl" in config._engine_options(production=True)["connect_args"]


class TestLoadConfig:
    def test_production_config_with_an_aiven_style_url(self, monkeypatch, ca_pem):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem)
        monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://other.example.com")
        cfg = config.load_config("production")
        assert cfg["SQLALCHEMY_DATABASE_URI"].startswith("mysql+pymysql://avnadmin:")
        assert "ssl-mode" not in cfg["SQLALCHEMY_DATABASE_URI"]
        assert cfg["DEBUG"] is False
        assert cfg["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["ssl"].verify_mode == ssl.CERT_REQUIRED
        assert cfg["CORS_ORIGINS"] == ["https://app.example.com", "https://other.example.com"]

    def test_the_testing_config_is_untouched(self):
        cfg = config.load_config("testing")
        assert cfg["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")
        assert "SQLALCHEMY_ENGINE_OPTIONS" not in cfg

    def test_a_production_config_needs_real_secrets(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("SECRET_KEY", "short")
        with pytest.raises(RuntimeError):
            config.load_config("production")

    def test_the_app_factory_builds_with_the_production_config_and_never_connects(self, monkeypatch, ca_pem):
        monkeypatch.setenv("DATABASE_URL", AIVEN)
        monkeypatch.setenv("DB_SSL_CA_PEM", ca_pem)
        from app import create_app
        app = create_app("production")
        assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql+pymysql://")
        assert app.config["DEBUG"] is False
