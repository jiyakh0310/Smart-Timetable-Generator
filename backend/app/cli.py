"""Flask CLI commands:  flask --app run seed-demo | create-admin"""
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
