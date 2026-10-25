# Smart Timetable Management and Automated Classroom Allocation System

Web application that generates conflict-free timetables and allocates classrooms by batch size and room type.
**Stack:** React + Vite · Python Flask · MySQL · SQLAlchemy + Alembic migrations.
**Roles:** Admin, Faculty, Student (no Department Head role - see `docs/requirements-mapping.md`).

## Current status: M1 + UI redesign (top navigation, no-scroll responsive tables) + Time slots (R6) + Subjects (R4) + Batches & Students (R3) + Faculty (R2) & availability (R13) + Teaching assignments + Rooms & labs (R5) with clash/allocation checks (R8, R9) + Timetable generation (R7) + Timetable validation (R10) + Faculty workload limits (R14) + Manual timetable editing (R15) + Approval and publishing (R16) + Faculty / student published timetable views (R11, R12) + PDF / Excel export (R18)

| Done in M1 | Not built yet |
|---|---|
| Flask app foundation, MySQL config, migrations | Faculty / student / subject / room CRUD (M2-M3) |
| Shared database models (all tables) | Timetable generator and validation (M4) |
| Login, JWT sessions, backend role checks, change password | Publishing, editing, approval, exports (M5-M8) |
| React shell, Admin / Faculty / Student dashboards | Optional features (M9) |
| Demo data and demo accounts | |

Screens for unbuilt features show a clearly labelled "Not built yet" page naming the owner, requirement and milestone.

## Team and module ownership

| Member | Module | Requirements | Backend | Frontend |
|---|---|---|---|---|
| Isha | User & Faculty Management | R1, R2, R13, R14, R19 | `backend/app/modules/isha` | `frontend/src/features/isha` |
| Diya | Student & Academic Management | R3, R4, R6, R12, R22 | `backend/app/modules/diya` | `frontend/src/features/diya` |
| Pragya | Classroom & Conflict Management | R5, R8, R9, R23 | `backend/app/modules/pragya` | `frontend/src/features/pragya` |
| Jiya | Timetable Generation & Publishing | R7, R10, R11, R15, R16, R18 | `backend/app/modules/jiya` | `frontend/src/features/jiya` |

Shared code (written once): `backend/app/models`, `backend/app/common`, `frontend/src/components`, `frontend/src/services`.
Details: `docs/module-ownership.md`, `docs/requirements-mapping.md`.

## Prerequisites (Windows)

- Python 3.12, Node.js 20+ (22 tested), npm, MySQL 8 + MySQL Workbench

## Setup

### 1. Create the database and an application user (MySQL Workbench)

Open a connection as an admin user, then run (choose your own password):

```sql
CREATE DATABASE smart_timetable CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'timetable_app'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON smart_timetable.* TO 'timetable_app'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Configure environment variables

From the project root (PowerShell):

```powershell
copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"    # run twice; paste into SECRET_KEY and JWT_SECRET_KEY
notepad .env                                               # set DB_USER, DB_PASSWORD (and the two secrets)
```

`.env` is git-ignored. The app refuses to start while secrets or DB settings are still placeholders.

### 3. Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app run db upgrade        # creates all tables from the migration
flask --app run seed-demo         # development demo data + demo accounts
python run.py                     # API on http://127.0.0.1:5000
```

If PowerShell blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

Check it: open <http://127.0.0.1:5000/api/v1/health> - expect `"status": "ok"` (this also proves the MySQL connection works).

### 4. Frontend (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (normally <http://localhost:5173>; if that port is busy Vite picks the next free one and prints it). Calls to `/api` are proxied to Flask on port 5000.

## Demo accounts (development only)

Created by `seed-demo`; password is `Demo@12345` unless you set `DEMO_PASSWORD` in `.env`. The command refuses to run when `APP_ENV=production`.

| Role | Email |
|---|---|
| Admin | `admin@timetable.test` |
| Faculty | `faculty1@timetable.test` ... `faculty6@timetable.test` |
| Student | `student1@timetable.test` ... `student4@timetable.test` |

For a real administrator account: `flask --app run create-admin`.

## Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

Tests use an in-memory SQLite database, so they do not touch your MySQL data. See `docs/testing-plan.md`.

## Frontend tests and production build

```powershell
cd frontend
npm test            # Vitest + Testing Library
npm run build
```

## Documentation

`docs/requirements-mapping.md` · `docs/module-ownership.md` · `docs/database-design.md` · `docs/api-contracts.md` · `docs/testing-plan.md` · `docs/ui-design-system.md`
