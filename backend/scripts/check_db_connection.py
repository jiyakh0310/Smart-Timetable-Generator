"""Check the real MySQL connection using exactly the settings the app uses.

Run from the backend folder (venv active):   python scripts/check_db_connection.py
Never prints the password or secrets.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PROJECT_ROOT, _database_uri  # noqa: E402  (loads PROJECT_ROOT/.env)
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

print(f".env file used : {PROJECT_ROOT / '.env'}  (exists: {(PROJECT_ROOT / '.env').exists()})")
print(f"DATABASE_URL   : {'SET - overrides DB_* values' if os.getenv('DATABASE_URL') else 'not set (DB_* values are used)'}")

try:
    url = make_url(_database_uri())
except RuntimeError as err:
    sys.exit(f"CONFIG PROBLEM: {err}")

print(f"Connecting as  : {url.username}@{url.host}:{url.port}/{url.database}  (password: {len(url.password or '')} characters, hidden)")

try:
    with create_engine(url).connect() as conn:
        version, user, database = conn.execute(text("SELECT VERSION(), CURRENT_USER(), DATABASE()")).one()
        tables = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")).scalar()
    print(f"SUCCESS        : MySQL {version}, logged in as {user}, database '{database}', {tables} table(s) present")
except SQLAlchemyError as err:
    print("FAILED         :", str(getattr(err, "orig", err)))
    sys.exit(1)
