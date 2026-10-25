"""Flask CLI commands:  flask --app run seed-demo | create-admin | db-check"""
import click
from flask import current_app

from app.extensions import db
from app.models import Role, User
from app.seed import demo_password, seed_demo_data


def register_cli(app):
    @app.cli.command("seed-demo")
    def seed_demo():
        """Load realistic DEMO data and demo accounts (development only)."""
        if current_app.config["APP_ENV"] == "production":
            raise click.ClickException("Refusing to load demo accounts when APP_ENV=production.")
        summary = seed_demo_data()
        click.echo("Demo data ready: " + ", ".join(f"{k}={v}" for k, v in summary.items()))
        click.echo("Demo accounts (DEVELOPMENT ONLY):")
        click.echo("  admin@timetable.test, faculty1..6@timetable.test, student1..4@timetable.test")
        click.echo(f"  password: {demo_password()}")

    @app.cli.command("db-check")
    def db_check():
        """Read-only database connection check: shows the TLS mode and, on failure, the redacted reason and what to change."""
        from sqlalchemy import text

        from app import config as cfg
        from app.common import db_diagnostics

        url = db.engine.url
        click.echo(f"driver={url.drivername}  host={url.host}  port={url.port}  database={url.database}  user={url.username}")
        ctx = current_app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}).get("connect_args", {}).get("ssl")
        if ctx is None:
            click.echo("TLS: off")
        else:
            click.echo(f"TLS: {cfg._tls_mode()}  (certificate required: {ctx.verify_mode.name == 'CERT_REQUIRED'}, host name checked: {ctx.check_hostname}, trusted CA certificates: {len(ctx.get_ca_certs())})")
        try:
            with db.engine.connect() as conn:
                click.echo(f"SELECT 1: {conn.execute(text('SELECT 1')).scalar()}")
                cipher = conn.execute(text("SHOW SESSION STATUS LIKE 'Ssl_cipher'")).first()
                click.echo(f"TLS cipher in use: {(cipher[1] if cipher else '') or 'none (connection is NOT encrypted)'}")
                click.echo(f"tables in this database: {conn.execute(text('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()')).scalar()}")
        except Exception as exc:  # noqa: BLE001 - report every kind of failure the same way
            reason = db_diagnostics.classify(exc)
            click.echo(f"FAILED [{reason}]: {db_diagnostics.safe_message(exc)}")
            click.echo(f"What to change: {db_diagnostics.HINTS[reason]}")
            raise SystemExit(1) from None
        click.echo("OK")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Full name")
    @click.password_option()
    def create_admin(email, name, password):
        """Create a real administrator account (works in any environment)."""
        email = email.strip().lower()
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        if db.session.scalar(db.select(User).filter_by(email=email)):
            raise click.ClickException(f"A user with email {email} already exists.")
        user = User(email=email, full_name=name.strip(), role=Role.ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin created: {email}")
