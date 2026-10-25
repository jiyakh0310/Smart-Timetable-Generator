# Module Ownership

One shared application; each member owns a feature folder on both backend and frontend. Shared building blocks are defined once.

## Shared (written once)

| Area | Location |
|---|---|
| Database models (single source) | `backend/app/models/` |
| Migrations | `backend/migrations/` |
| API envelope, errors, role checks, validation | `backend/app/common/` |
| Config and extensions | `backend/app/config.py`, `backend/app/extensions.py` |
| UI components, API client, app shell | `frontend/src/components`, `frontend/src/services`, `frontend/src/app` |

## Members

### Member 1 - Isha: User & Faculty Management
R1, R2, R13, R14, R19
- Backend: `backend/app/modules/isha/` (`routes.py`, `services.py`)
- Frontend: `frontend/src/features/isha/`
- Tests: `backend/app/tests/isha/`
- **M1 delivered:** `/api/v1/auth/login`, `/me`, `/change-password`; backend `@role_required` (in `common/auth.py`); `LoginForm`, `ChangePasswordForm`.
- **M3A delivered:** **R2 faculty management** and **R13 admin-managed availability** (`isha/faculty_*.py`, `isha/availability_service.py`, `features/isha/FacultyPage.jsx`, `AvailabilityPage.jsx`). Still planned: R14 workload, faculty self-service availability, R19 announcements.

### Member 2 - Diya: Student & Academic Management
R3, R4, R6, R12, R22
- Backend: `backend/app/modules/diya/` · Frontend: `frontend/src/features/diya/`
- Models used: `Batch`, `Student`, `Subject`, `TimeSlot`, `TeachingAssignment`, `AcademicTerm`, `Department`, `Program`
- **Delivered:** M1 models + demo data; **M2: R6 time slots** (`diya/time_slot_*.py`, `features/diya/TimeSlotsPage.jsx`) **R4 subjects** (`diya/subject_*.py`, `features/diya/SubjectsPage.jsx`) and **R3 batches + students** (`diya/batch_*.py`, `diya/student_*.py`, `features/diya/BatchesPage.jsx`, `StudentsPage.jsx`). **Teaching assignments** (`diya/assignment_*.py`, `features/diya/AssignmentsPage.jsx`) - placed with Diya because the API contract always listed `/teaching-assignments` under her module; it consumes Isha's faculty and availability data.

### Member 3 - Pragya: Classroom & Conflict Management
R5, R8, R9, R23
- Backend: `backend/app/modules/pragya/` · Frontend: `frontend/src/features/pragya/`
- Models used: `Room`, `Equipment`
- Provides to others: `check_entry`, `validate_timetable`, `rank_rooms` (see `api-contracts.md`)
- **M4A delivered:** **R5 rooms & labs** (`pragya/room_service.py`, `room_routes.py`, `features/pragya/RoomsPage.jsx`) and the **R8/R9 reusable checks** (`pragya/clash_service.py`, `clash_routes.py`): `check_session`, `validate_timetable`, `rank_rooms`, `explain_rooms`. Still planned: R23 equipment-based allocation.

### Member 4 - Jiya: Timetable Generation & Publishing
R7, R10, R11, R15, R16, R18 (and R17 versioning)
- Backend: `backend/app/modules/jiya/` · Frontend: `frontend/src/features/jiya/`
- Models used: `Timetable`, `TimetableEntry`, `UnscheduledItem`
- Consumes the other three modules' services; owns the generator.
- **M1 delivered:** the models only. Logic arrives in M4.

## Integration rule
Modules call each other through documented service functions (`api-contracts.md`), never by copying logic or defining their own models.

## Jiya - R7 delivered (M5)
- **Backend:** `jiya/generator.py` (pure planner), `jiya/timetable_service.py` (persistence, versions, rollback, discard), `jiya/timetable_routes.py` (`/api/v1/timetables`, Admin only). It reuses Pragya's `check_session`, `rank_rooms`, `explain_rooms` and `validate_timetable`; no clash rule is duplicated. Pragya's `clash_service` gained an optional `PlanningContext` read-through cache (default behaviour unchanged).
- **Frontend:** `features/jiya/TimetablesPage.jsx`, `GenerateDialog.jsx`, `TimetableDetail.jsx`, `timetables.js`.
- Still planned for Jiya: R10 validation workflow, approval/publishing, manual editing (R15), exports (R16), notifications.

## Jiya - R10 delivered
- **Backend:** `jiya/validation_service.py` (`POST /api/v1/timetables/:id/validate`). It calls `clash_service.validate_timetable` for every hard rule and adds the completeness check; no rule is duplicated.
- **Frontend:** `features/jiya/ValidationResult.jsx` and a Validate action in `TimetableDetail.jsx`; the list shows the recorded validation state.
- Still planned for Jiya: approval and publishing (R16, R11), manual editing (R15), exports (R18), notifications.

## Isha - R14 delivered
- **Backend:** `isha/workload_service.py` is the single place that measures teaching duration and compares it with `faculty.max_weekly_hours`. The generator (`jiya/generator.py`), the validator (`jiya/validation_service.py`) and the timetable detail all call it; the clash service is unchanged.
- **Frontend:** `features/jiya/WorkloadTable.jsx`, shown in the generation summary and the timetable detail, plus a pre-generation warning in the Generate dialog.
- Still planned for Isha: R19 announcements, faculty self-service availability.

## Jiya - R15 delivered
- **Backend:** `jiya/edit_service.py` (`PATCH /api/v1/timetables/:id/entries/:entry_id` and `GET .../edit-options`). It reuses `check_session`, `rank_rooms`, `workload_service` and `validation_service.evaluate`; no rule is duplicated.
- **Frontend:** `features/jiya/EditEntryDialog.jsx`; the weekly grid in `TimetableDetail.jsx` becomes clickable for editable timetables (`WeeklyTimetable` gained an optional `onEntryClick`).
- Still planned for Jiya: approval and publishing (R16, R11), exports (R18), notifications.

## Jiya - R16 delivered
- **Backend:** `jiya/approval_service.py` (`POST /api/v1/timetables/:id/submit|approve|reject|publish`). `TRANSITIONS` in `timetable_service.py` is the single source of truth for the allowed moves. Validation is `validation_service.evaluate`; no rule is duplicated.
- **Frontend:** `features/jiya/ReviewPanel.jsx` (workflow steps, confirmations, reject dialog) inside the timetable detail; a "Current" badge in the list; `TextAreaField` added to the design system.
- There is no separate reviewer: the system has exactly three roles, so the Admin reviews, approves and publishes (approved scope decision). Still planned for Jiya: exports (R18), notifications; R12/R11 viewing for students and faculty.

## Faculty and student views (R11 / R12) delivered
- **Backend:** `jiya/published_service.py` and `published_routes.py` (`GET /api/v1/faculty/timetable`, `GET /api/v1/student/timetable`). R12 belongs to Diya and the faculty view to Jiya; both share one small read-only service so the visibility rules live in one place.
- **Frontend:** `features/jiya/MyTimetablePage.jsx` (used by `/faculty/timetable` and `/student/timetable`), `published.js`; the two dashboards link to it.

## Export (R18) delivered
- **Backend:** `jiya/export_service.py` (what may be exported, and the Document), `jiya/export_render.py` (PDF with reportlab, Excel with openpyxl), routes added to `timetable_routes.py` (Admin) and `published_routes.py` (Faculty, Student).
- **Frontend:** `features/jiya/ExportButtons.jsx`, `services/download.js` and `api.download` (an authenticated file download; a plain link cannot send the bearer token).
- Dependencies added: `openpyxl`, `reportlab` (and their transitive `pillow`, `charset-normalizer`, `et-xmlfile`), pinned in `requirements.txt`. Still planned: notifications, restore/compare (R17).
