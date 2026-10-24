# Database Design

MySQL 8, accessed through SQLAlchemy; schema is created only by Alembic migrations (`backend/migrations`). Naming conventions give every constraint a stable name. Enums are stored as short VARCHARs holding the value. Models live in `backend/app/models/`.

## Tables

| Table | Key columns | Constraints |
|---|---|---|
| `users` | email, password_hash, full_name, role (admin/faculty/student), is_active, last_login | email unique |
| `departments` | code, name | code unique |
| `programs` | department_id, name, duration_semesters | unique (department, name) |
| `academic_terms` | name, academic_year, term_type (odd/even), dates, is_active | name unique |
| `faculty` | user_id, employee_code, department_id, designation, max_weekly_hours | user_id unique, employee_code unique, hours > 0 |
| `faculty_availability` | faculty_id, time_slot_id, status (available/unavailable/preferred) | unique (faculty, slot); no row = available |
| `batches` | program_id, department_id, semester_no, section, name, strength | unique (program, semester, section); strength > 0 |
| `students` | user_id (nullable), enrollment_no, name, email, batch_id | enrollment_no unique; user_id unique |
| `subjects` | code, name, department_id, semester_no, credits, weekly_hours, class_type (theory/lab), lab_block_periods, required_room_type | code unique; credits >= 0; hours > 0; block >= 1 |
| `equipment`, `room_equipment`, `subject_equipment` | optional R23 | composite primary keys |
| `rooms` | code, name, location, capacity, room_type, lab_type, is_available | code unique; capacity > 0 |
| `time_slots` | day_of_week (0=Mon), period_no, start_time, end_time, slot_type (class/break), is_active | unique (day, period); start < end; day 0-6 |
| `teaching_assignments` | term_id, batch_id, subject_id, faculty_id, sessions_per_week | unique (term, batch, subject); sessions > 0 |
| `timetables` | term_id, name, version, status, validation_passed, generated_by, approved_by, rejection_reason, published_at | unique (term, version) |
| `timetable_entries` | timetable_id, assignment_id, faculty_id, batch_id, room_id, time_slot_id | **unique (timetable, faculty, slot)**, **(timetable, batch, slot)**, **(timetable, room, slot)** |
| `unscheduled_items` | timetable_id, assignment_id, session_no, reason_code, reason_text | - |
| `announcements` | title, message, audience, batch_id, status, created_by, published_at | - |
| `system_settings` | key, value, description | key is primary key |

## Relationships (summary)
`users` 1-1 `faculty` / `students`; `departments` -> `programs` -> `batches` -> `students`; `teaching_assignments` link term + batch + subject + faculty; `timetables` 1-N `timetable_entries` (each pointing to an assignment, faculty, batch, room, slot).

## Design notes
- **Clash rules at two levels.** Python services (Pragya) explain a clash to the user; the three unique constraints on `timetable_entries` are a database safety net that makes a double-booking impossible even if code is wrong. Tests for these constraints exist.
- **Overlap = same slot.** Slots on one weekday must not overlap (enforced by the time-slot service since M2; the database itself only enforces unique day + period and start < end), so "same `time_slot_id`" is the same as "overlapping time". Back-to-back slots (10:00 end / 10:00 start) do not clash.
- **Labs** occupy `lab_block_periods` consecutive class periods; each period is one `timetable_entries` row.
- **Versions.** Each generation creates a new `timetables` row with the next version number for its term.
- **Deviation from the SRS:** `teaching_assignments` and the equipment tables are additions; the SRS had 8 entities.
- **Deletion.** Foreign keys are restrictive by default, so rooms/subjects/etc. that are in use cannot be silently deleted; services will return a clear message (M2/M3).

## Time-slot rules added in M2 (application level, no schema change)
- No two slots on the same weekday overlap in time (half-open: 09:00-10:00 and 10:00-11:00 are fine).
- Period numbers follow time order within a day, because lab sessions use consecutive periods.
- A slot referenced by `timetable_entries` or `faculty_availability` cannot be deleted (the database would silently cascade-delete availability rows, so the service blocks it); it can be disabled with `is_active = false`.
- A slot used by a timetable cannot have its day, period or times changed.
- The existing schema was sufficient for R6; no migration was needed.

## Subject rules added in M2 (application level, no schema change)
- Codes are normalised to UPPER CASE before saving because MySQL's `utf8mb4_unicode_ci` treats `cs301` and `CS301` as the same key while SQLite does not.
- Labs must require a laboratory and their weekly hours must be a whole number of lab sessions; theory subjects cannot require a laboratory.
- `teaching_assignments.sessions_per_week` is copied from the subject when an assignment is created, so a subject with assignments cannot change department, semester, type, weekly hours or lab length (it can still change name, code, credits and room type).
- A subject with teaching assignments cannot be deleted (the foreign key would otherwise surface as a raw database error).
- **Not representable in the current schema (needs your decision before any migration):** a "course handout" (appears only in the hand-drawn architecture sketch) and separate theory-hours / lab-hours on one subject (the sketch's "Theory/Lab hour"; today a subject is either theory or lab, so a course with both parts is entered as two subjects, as in the seed data). The SRS "Subject -> Faculty" link is handled by `teaching_assignments`.

## Batch and student rules added in M2 (application level, no schema change)
- `batches.strength` is **stored** (it is the planned class size used for room allocation); student records are a partial list, so it is not computed. It may not be lower than the number of students already in the batch, and a full batch rejects further students, so the stored number never understates reality.
- `batches` has both `program_id` and `department_id`; the API always derives the department from the program so they cannot disagree.
- Section and enrollment numbers are normalised to UPPER CASE (MySQL's `utf8mb4_unicode_ci` compares them case-insensitively, SQLite does not). Student emails are lower-cased and must not be shared (the table itself only enforces unique `enrollment_no` and `user_id`).
- A batch referenced by `students`, `teaching_assignments`, `timetable_entries` or `announcements` cannot be deleted; program and semester are locked while it has assignments or timetable entries.
- The `students` table has no active/inactive flag, so records are removed by deleting them; deleting a student also sets the linked user's `is_active` to false (the user row is kept).
- **Not changed, for your decision:** there is no way yet to create or link a student's login (`students.user_id`); account management belongs to the user/faculty module (Isha).

## Faculty and availability rules added in M3A (application level, no schema change)
- `faculty.user_id` is NOT NULL and unique, so a faculty member and their login are strictly 1:1: creating faculty creates a `users` row with role `faculty` in the same transaction; deleting faculty (only when unreferenced) deletes both. The role can never be supplied by a client.
- Deactivation uses the existing `users.is_active` flag; the app already rejects inactive accounts on every request. No new column was needed.
- Employee codes are upper-cased and emails lower-cased because MySQL's `utf8mb4_unicode_ci` compares them case-insensitively while SQLite does not. Emails must be unique across all roles (the `users.email` unique key).
- `faculty_availability` semantics: `unavailable` = hard constraint, `preferred` = soft preference (must never be treated as a requirement), `available` = default with **no row stored**. Rows for slots that are later disabled are preserved. The time-slot service refuses to delete a slot that has availability rows because the database would otherwise silently cascade-delete them.
- **Proposed, not applied (needs your approval):** `users.must_change_password BOOLEAN NOT NULL DEFAULT false`. Today the Admin sets an initial password and shares it; there is no forced change on first login and no email-based reset. The flag would let the app require a new password at first sign-in. Authentication code and one migration would change, so it is left as a decision for you.
- JWTs are stateless: after a password reset, sessions that are already signed in stay valid until their normal expiry (8 h by default). Deactivation is immediate because the user row is checked on every request.

## Teaching-assignment rules added in M3B (application level, no schema change)
- `teaching_assignments.sessions_per_week` is **derived data**: the service computes it from the subject (theory: weekly hours; lab: weekly hours / lab session length) and never accepts it from a client. Updating an assignment's subject recomputes it. The session *length* is not stored on the assignment; it always comes from the subject (`lab_block_periods`, or 1 for theory).
- (term, batch, subject) is unique, so a batch has exactly one teacher per subject per term; the service reports the clash with the current teacher's name before the database constraint is reached.
- Subject and batch must share a semester. Departments may differ (flagged, not blocked) because shared subjects are legitimate and no document forbids them.
- An assignment referenced by `timetable_entries` or `unscheduled_items` (neither cascades) is frozen and cannot be deleted. There is no timetable-deletion API yet, so such an assignment stays locked until the generator milestones add a way to remove or regenerate a timetable.
- Availability never blocks an assignment. `faculty_availability` rows of status `unavailable` (hard) shrink the usable slots used for warnings; `preferred` (soft) is ignored there.
- "Consecutive periods" is defined as period numbers that differ by 1 on the same day among active class slots. Because a break occupies its own period number, two periods on either side of a break are not consecutive. If you want labs allowed across a break, that definition (and the generator) would change.

## Rooms and clash-check rules added in M4A (application level, no schema change)
- Room codes are upper-cased (MySQL's `utf8mb4_unicode_ci` compares them case-insensitively, SQLite does not). The equipment tables exist but are unused until the optional R23 feature.
- The only reference to a room is `timetable_entries.room_id` (no cascade). While entries reference a room it cannot be deleted, its type is locked and its capacity cannot fall below the largest batch scheduled in it. Taking it out of service stays possible and is reported by validation.
- **Overlap is decided from times, not slot ids.** The unique keys on `timetable_entries` (timetable + faculty/batch/room + slot) only catch the *same slot row*. The Time Slots module prevents overlapping slots from being created, but the clash service still compares `[start, end)` intervals so misconfigured or legacy slot data cannot hide a clash. Touching intervals are not overlaps.
- **Hard vs soft:** `faculty_availability.status = unavailable` is a hard conflict; `preferred` can only produce the advisory `outside_preferred_slots` and never blocks a placement.
- **Not checked by the clash service (on purpose):** workload limits (R14) and timetable completeness (R10).
- The room type rule: lab subject -> laboratory; theory subject -> never a laboratory and, when the subject names a `required_room_type`, exactly that type.

## Timetable generation rules added in R7 (application level, no schema change, no migration)
- `timetables` has no batch/scope column, so a generation covers a whole term. `version` = `max(version) + 1` per term (`uq_timetables_term_version` is the safety net); status is always `draft`, `validation_passed` stays false (that is R10's job).
- `timetable_entries` get one row per **period** (a 2-period lab = 2 rows with the same assignment, faculty, batch and room). `unscheduled_items` get one row per missing **session** with `reason_code` and `reason_text`.
- While a timetable references them, assignments, rooms, subjects, batches, faculty and time slots are frozen by the existing in-use guards. Only a draft can be discarded (cascade removes its entries and unscheduled items).
- Heuristic: sessions are placed most-constrained first (fewest feasible windows, then labs, then larger batches, then id). Soft score per candidate window: preferred periods (+10 per period outside), same subject twice on a day (+6), periods the batch already has that day (+1 each); ties go to the earliest day/period. Hard rules always come from `clash_service`.

## Validation rules added in R10 (application level, no schema change, no migration)
- Uses the existing `timetables.validation_passed` and `validated_at`. `validation_passed` is true only when the last validation found no hard error and the timetable was complete; it is a snapshot (the setup data a timetable depends on can still change afterwards, so re-validate before relying on it).
- Required sessions are `teaching_assignments.sessions_per_week` for the timetable's term, read at validation time. Scheduled sessions are entry rows per assignment divided by the session length (1 for theory, `lab_block_periods` for a lab).
- Status movement made by validation: `draft` -> `validated` on a pass, `validated` -> `draft` on a failure; nothing else.
