# API Contracts

## Conventions
- Base path `/api/v1`. JSON only.
- Success: `{ "success": true, "data": ..., "message": "optional" }`
- Failure: `{ "success": false, "error": { "code": "...", "message": "...", "details": { "field": "msg" } } }`
- Auth: `Authorization: Bearer <JWT>` (expires after `JWT_EXPIRES_HOURS`, default 8).
- Status codes: 400 validation, 401 not signed in / bad token, 403 wrong role, 404 not found, 409 conflict/in use, 503 database down.
- Authorization is enforced in Flask by `@role_required(Role.X)`; the role is read from the database on every request.

## Implemented in Milestone 1

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/health` | public | `{status: "ok"}`; 503 if the database is unreachable |
| POST | `/auth/login` | public | body `{email, password}` -> `{token, user}`; 400 blank fields; 401 `invalid_credentials` (same message for wrong email, wrong password, disabled account) |
| GET | `/auth/me` | any signed-in | user + `faculty` or `student` profile |
| POST | `/auth/change-password` | any signed-in | body `{current_password, new_password}`; min 8 chars, must differ |
| GET | `/admin/summary` | admin | real counts and timetable counts by status |

### Milestone 2: Time slots (R6, Diya)
List endpoints share one shape: `data = { items, page, per_page, total, pages }`; query `page` (>=1), `per_page` (1-100, default 20); invalid values are 400.

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/time-slots` | any signed-in | filters `day` (0=Mon..6=Sun), `slot_type` (class/break), `active` (true/false); search `q` = period number or time prefix (`09:`); ordered by day, period |
| GET | `/time-slots/:id` | any signed-in | 404 if missing |
| POST | `/time-slots` | admin | body `{days:[0..6], period_no (1-20), start_time "HH:MM", end_time, slot_type?, is_active?}`; creates the period on every listed day, **all-or-nothing**; 201 `{items:[...]}` |
| PATCH | `/time-slots/:id` | admin | any of `day_of_week, period_no, start_time, end_time, slot_type, is_active`; unknown fields rejected |
| DELETE | `/time-slots/:id` | admin | 409 `slot_in_use` if a timetable entry or faculty availability references it (disable instead) |

Item: `{id, day_of_week, day_name, period_no, start_time, end_time, slot_type, is_active, in_use, usage:{timetable_entries, faculty_availability}}`.

Errors: 400 `validation_error` (with per-field `details`: bad time format, end <= start, day outside 0-6, period outside 1-20, empty/duplicate `days`, unknown field); 409 `duplicate_slot` (same day + period), 409 `overlapping_slot` (times overlap another slot on that day; back-to-back is allowed), 409 `invalid_period_order` (period numbers must follow time order within a day), 409 `slot_in_use` (delete, or moving the day/period/times of a slot a timetable uses).

### Milestone 2: Subjects (R4, Diya)
Same list shape and paging as time slots. Read: any signed-in user. Write: Admin only.

| Method | Path | Notes |
|---|---|---|
| GET | `/subjects` | filters `department_id`, `semester_no` (1-12), `class_type` (theory/lab); search `q` matches code or name (case-insensitive, `%` and `_` are literal); ordered by code |
| GET | `/subjects/:id` | 404 if missing |
| POST | `/subjects` | body `{code, name, department_id, semester_no, credits, weekly_hours, class_type, lab_block_periods?, required_room_type?}`; 201 |
| PATCH | `/subjects/:id` | any subset of the same fields; unknown fields rejected |
| DELETE | `/subjects/:id` | 409 `subject_in_use` if the subject has teaching assignments |
| GET | `/departments` | read-only lookup `{items:[{id,code,name}]}` for dropdowns (not paginated, no write endpoints yet) |

Item: `{id, code, name, department:{id,code,name}, semester_no, credits, weekly_hours, class_type, lab_block_periods, required_room_type, sessions_per_week, usage:{teaching_assignments, timetable_entries}, in_use}`.

Rules: code is trimmed and stored UPPER CASE (letters, digits, `. _ / -`, max 20) and is unique case-insensitively; name 2-150 chars; semester 1-12; credits 0-20; weekly hours 1-40; the department must exist. **Lab:** `lab_block_periods` 1-6 (default 2), `weekly_hours` must be a multiple of it, room must be a laboratory (default). **Theory:** room is classroom (default), seminar hall or auditorium, never a laboratory; `lab_block_periods` is not accepted. `sessions_per_week` = hours / lab length for labs, else hours.
Errors: 400 `validation_error` with per-field `details`; 409 `duplicate_subject`; 409 `subject_in_use` (delete, or changing department, semester, type, weekly hours or lab length while teaching assignments exist; name, code, credits and room type stay editable).

### Milestone 2C: Batches and Students (R3, Diya)
Same list shape and paging as the other modules.

**Batches** (`/batches`) - read: any signed-in user (no personal data); write: Admin only.

| Method | Path | Notes |
|---|---|---|
| GET | `/batches` | filters `department_id`, `program_id`, `semester_no`; search `q` matches name or section; ordered by department, semester, section |
| GET | `/batches/:id` | 404 if missing |
| POST | `/batches` | body `{program_id, semester_no, section, strength, name?}`; name is generated (`CSE Sem 4 - A`) when blank; 201 |
| PATCH | `/batches/:id` | any subset of the same fields |
| DELETE | `/batches/:id` | 409 `batch_in_use` if students, teaching assignments, timetable entries or announcements reference it |
| GET | `/programs` | read-only lookup `{items:[{id,name,duration_semesters,department}]}` |

Item: `{id, name, section, semester_no, strength, student_count, seats_left, program, department, usage:{students, teaching_assignments, timetable_entries, announcements}, in_use, scheduled}`.
Rules: the department always comes from the program (clients cannot send `department_id`); semester 1..program duration; section 1-10 letters/digits stored UPPER CASE; strength 1-500; (program, semester, section) and the name must be unique (409 `duplicate_batch`). **Strength is a stored, admin-entered number**; it can never be set below the number of student records already in the batch (409 `strength_too_low`). Program and semester are locked (409 `batch_in_use`) once the batch has teaching assignments or timetable entries; name, section and strength stay editable.

**Students** (`/students`) - **every operation is Admin only, including reads** (personal data). A student sees their own profile via `/auth/me`.

| Method | Path | Notes |
|---|---|---|
| GET | `/students` | filters `batch_id`, `semester_no`, `department_id`; search `q` matches enrollment number, name or email; ordered by enrollment number |
| GET | `/students/:id` | |
| POST | `/students` | body `{enrollment_no, name, email?, batch_id}`; 201 |
| PATCH | `/students/:id` | any subset; `user_id` (login link) is not accepted |
| DELETE | `/students/:id` | also **disables the linked login account** (kept, `is_active=false`); response `{login_disabled}` |

Item: `{id, enrollment_no, name, email, has_login, batch:{id,name,semester_no,section,department_code}}` (the internal `user_id` is never returned).
Rules: enrollment number up to 30 chars (letters, digits `. _ / -`), stored UPPER CASE, unique regardless of case (409 `duplicate_student`); email optional, lower-cased, unique among students; the batch must exist and **have room** - adding or moving a student into a full batch is 409 `batch_full` ("increase the batch strength first"). A student whose batch is unchanged is never re-checked, so existing data stays editable.

### Milestone 3A: Faculty and availability (R2, R13, Isha) - every endpoint is Admin only, including reads
A faculty member sees their own profile through `/auth/me`; they cannot list colleagues or change availability.

| Method | Path | Notes |
|---|---|---|
| GET | `/faculty` | filters `department_id`, `active` (true/false); search `q` matches employee code, name or email; ordered by employee code |
| GET | `/faculty/:id` | 404 if missing |
| POST | `/faculty` | body `{name, email, employee_code, department_id, designation?, max_weekly_hours? (default 18), password}`; creates the faculty record **and** its login (role fixed to `faculty`) in one transaction; 201 |
| PATCH | `/faculty/:id` | any of `name, email, employee_code, department_id, designation, max_weekly_hours, is_active`; `role`, `user_id` and `password` are rejected (400) |
| POST | `/faculty/:id/reset-password` | body `{password}`; Admin sets a new password (hashed; never returned) |
| DELETE | `/faculty/:id` | 409 `faculty_in_use` if teaching assignments or timetable entries exist (deactivate instead); otherwise removes the record, its availability and its login |
| GET | `/faculty/:id/availability` | `{faculty, slots:[{time_slot_id, day_of_week, day_name, period_no, start_time, end_time, slot_type, is_active, status}], summary:{unavailable, preferred}}` - every time slot with the member's status (default `available`) |
| PUT | `/faculty/:id/availability` | body `{entries:[{time_slot_id, status}]}`; replaces the settings for all **active class** slots |

Item: `{id, employee_code, name, email, department, designation, max_weekly_hours, is_active, last_login, usage:{teaching_assignments, timetable_entries}, in_use, availability:{unavailable, preferred}}` (`password_hash` and `user_id` are never returned).
Rules: employee code up to 30 chars stored UPPER CASE, unique regardless of case; email lower-cased and unique across **all** accounts (admin, faculty, students); weekly hours 1-40. Password (create and reset): 8-128 characters with a letter and a number, not equal to the email, employee code or name. Duplicates -> 409 `duplicate_faculty`. **Deactivating** (`is_active=false`) disables the login immediately (existing tokens are rejected on the next request) and keeps every record.
Availability statuses: `unavailable` = **hard** (the generator must never schedule the faculty member in that slot), `preferred` = **soft** (favoured when possible, never required), `available` = default (no row stored; sending it removes a row). Only active class slots can be configured (breaks, disabled and unknown slots -> 400); duplicates in one request -> 400; rows that point at currently disabled slots are never deleted by a save. A time slot that still has availability rows cannot be deleted (see time slots).

### Milestone 3B: Teaching assignments (Admin only, including reads)
"Who teaches which subject to which batch in a term." Faculty and students will see their own subjects through their portal endpoints later.

| Method | Path | Notes |
|---|---|---|
| GET | `/teaching-assignments` | filters `term_id`, `batch_id`, `subject_id`, `faculty_id`, `semester_no`, `class_type`; search `q` matches subject code/name, batch name, faculty code/name; ordered newest term, batch, subject code |
| GET | `/teaching-assignments/:id` | |
| POST | `/teaching-assignments` | body `{term_id, batch_id, subject_id, faculty_id}` only; 201 |
| PATCH | `/teaching-assignments/:id` | any subset of the same four ids |
| DELETE | `/teaching-assignments/:id` | 409 `assignment_in_use` if timetable entries or unscheduled items reference it |
| GET | `/terms` | read-only lookup `{items:[{id,name,academic_year,is_active}]}`, any signed-in user |

Item: `{id, term, batch:{id,name,semester_no,strength,department_code}, subject:{id,code,name,class_type,semester_no,weekly_hours,lab_block_periods,department_code}, faculty:{id,employee_code,name,is_active}, sessions_per_week, session_length, periods_per_week, cross_department, session_mismatch, warnings:[{code,message}], usage:{timetable_entries, unscheduled_items}, in_use}`.

**Weekly requirement (always calculated by the server; a client-sent `sessions_per_week` is rejected with 400):** theory = `weekly_hours` sessions of 1 period; lab = `weekly_hours / lab_block_periods` sessions, each needing `lab_block_periods` **consecutive** periods (same day, period numbers differing by 1, so a lab cannot straddle a break). `periods_per_week = sessions_per_week x session_length`.
Rules: all four references must exist (400 on the field); the subject and the batch must be in the **same semester** (400 on `subject_id`); a department mismatch is allowed but flagged `cross_department`; the term must be active and the faculty member active when an assignment is created or those fields change; a batch has **one teacher per subject per term** (409 `duplicate_assignment`); a lab subject whose hours are not a whole number of sessions is refused. `session_mismatch` reports legacy drift between the stored count and the rule (an update recomputes it). **In use:** while timetable entries or unscheduled items reference an assignment, none of its four fields can change (409 `assignment_in_use`, reported before duplicate conflicts) and it cannot be deleted; an unchanged re-send is accepted.
**Availability warnings (informational, never blocking):** `availability_shortfall` when the faculty member's total required periods in the term exceed the active class slots not marked **unavailable**; `no_lab_window` when a lab needs N consecutive periods but no day has N of them free. Only **hard unavailability** reduces usable slots; a soft `preferred` never does.
Existing guards that this feature relies on (unchanged): a subject, batch or faculty member with assignments cannot be deleted, and a subject's hours/type/lab length and a batch's program/semester are locked.

### Milestone 4A: Rooms & labs, clash checks, room suggestions (Pragya) - Admin only, including reads

**Rooms** (`/rooms`, R5)

| Method | Path | Notes |
|---|---|---|
| GET | `/rooms` | filters `room_type`, `available` (true/false), `min_capacity`; search `q` matches code, name or location; ordered by code |
| GET | `/rooms/:id` | |
| POST | `/rooms` | body `{code, name, capacity, room_type, location?, lab_type?, is_available?}`; 201 |
| PATCH | `/rooms/:id` | any subset |
| DELETE | `/rooms/:id` | 409 `room_in_use` if timetable entries reference it (mark it unavailable instead) |
| GET | `/rooms/suggest` | `?batch_id&subject_id&time_slot_ids=3,4[&timetable_id]` -> `{suitable:[rooms, smallest first, with spare_seats], excluded:[room + reasons], slot_problems}` |

Item: `{id, code, name, location, capacity, room_type (classroom|lab|seminar_hall|auditorium), lab_type, is_available, usage:{timetable_entries}, min_capacity, in_use}`.
Rules: code up to 30 chars stored UPPER CASE, unique regardless of case (409 `duplicate_room`); capacity 1-2000; `lab_type` only for laboratories; blank optional text becomes null. A room that timetable entries reference: cannot be deleted, its **type is locked**, its **capacity cannot drop below the largest batch scheduled in it** (`min_capacity`; equal is allowed) - all 409 `room_in_use`. Marking it **unavailable is allowed** (rooms must be able to go out of service); the success message states how many entries are affected and validation will report them.

**Clash checks** (R8/R9)

| Method | Path | Notes |
|---|---|---|
| POST | `/conflicts/check` | body `{room_id, time_slot_ids, (assignment_id \| faculty_id + batch_id [+ subject_id]), timetable_id?, ignore_entry_ids?}` -> `{ok, hard_count, advisory_count, conflicts:[{code, severity, message, details}]}`; read-only |
| GET | `/conflicts/validate?timetable_id=N` | re-checks every saved entry -> `{timetable_id, is_valid, hard_count, advisory_count, conflicts}` |

`ok` / `is_valid` are false only when a **hard** conflict exists; **advisory** notes never change them.
**Precise definitions.** Periods overlap when they are on the same weekday and `a.start < b.end and b.start < a.end` (half-open): classes that merely touch (10:00 end / 10:00 start) do **not** overlap, and real times are compared so two different slot rows covering the same time are still caught. A session is the periods one class occupies: 1 for theory, `lab_block_periods` for a lab, which must be **consecutive** (same day, period numbers differing by 1; a break has its own period number, so periods either side of it are not consecutive).
Hard codes: `faculty_clash`, `batch_clash`, `room_clash` (details name the clashing entry), `room_too_small` (capacity < batch strength; equal is fine), `room_unavailable`, `room_type_mismatch` (a lab subject needs a laboratory, a theory subject cannot use one, and a subject's `required_room_type` must match), `slot_unknown`, `slot_is_break`, `slot_inactive`, `duplicate_slot`, `wrong_session_length`, `not_consecutive`, `faculty_unavailable` (**hard** availability), `lab_not_consecutive` (saved lab entries that do not form whole consecutive sessions). Advisory code: `outside_preferred_slots` (a faculty member has preferred slots and the session is outside them; a **soft preference is never a prohibition**).
Not done here: timetable completeness (every required class scheduled) belongs to R10.

### Milestone 5: Timetable generation (R7, Jiya) - Admin only, including reads

| Method | Path | Notes |
|---|---|---|
| POST | `/timetables/generate` | body `{term_id}` (only that field); 201 with the new draft and a `generation` summary |
| GET | `/timetables` | filters `term_id`, `status`; newest version first; paginated |
| GET | `/timetables/:id` | the timetable plus `entries` (one per period: batch, subject, faculty, room, time slot) and `unscheduled` (assignment, session number, `reason_code`, `reason_text`) |
| DELETE | `/timetables/:id` | discards a **draft** only (409 `timetable_not_draft` otherwise) |

Timetable item: `{id, term, name, version, status, validation_passed, generated_by, generated_at, periods, unscheduled_sessions, can_discard}`.
`generation`: `{status: complete|partial|none_scheduled, required_sessions, scheduled_sessions, unscheduled_sessions, scheduled_periods, unscheduled_reasons: {code: n}, warnings: [text]}`.
Errors: 400 `validation_error` (missing/invalid/unknown `term_id` or extra fields), 409 `term_inactive`, 409 `no_assignments`, 409 `generation_conflict` (a version race kept being lost), 500 `generation_invalid` (the generated result broke a hard rule; nothing is saved), 401/403.

**Scope.** One generation covers the whole term (every teaching assignment of the term): faculty and rooms are shared by all batches, so clashes can only be prevented by planning them together.
**Versions (R17).** Each generation creates `max(version) + 1` for the term as `draft` with `validation_passed = false`. Older versions are never modified or archived by generation. Version numbers are never reused while a higher one exists; if the highest draft is discarded its number is allocated again.
**Safety.** One transaction; the term row is locked while the version is allocated; the (term, version) unique key is the safety net with up to 3 retries; the saved rows are re-checked with `validate_timetable` and any hard conflict rolls everything back.
**Reason codes** (`unscheduled_items.reason_code`): `faculty_unavailable`, `faculty_inactive`, `faculty_busy`, `batch_busy`, `rooms_busy`, `no_suitable_room`, `no_consecutive_window`, `no_class_slots`, `no_free_slot`. Each comes with a readable `reason_text`.
**Discard (added to R7 on purpose).** Assignments, subjects, rooms, batches, faculty and time slots are frozen while any timetable references them. Without a way to remove a draft, the first generation would lock the setup data for good, so Admin can discard a draft (never an approved/published one). This is not the R17 restore/compare feature.

### Milestone 6: Timetable validation (R10, Jiya) - Admin only

| Method | Path | Notes |
|---|---|---|
| POST | `/timetables/:id/validate` | no body needed (any body is ignored); re-reads the SAVED rows, records the result, returns the report; 404 if unknown, 401/403 |

`GET /conflicts/validate?timetable_id=N` (M4A) stays as the read-only hard-rule check; it records nothing and has no completeness part.

Report (`data`): `{timetable_id, status, validation_passed, is_valid, is_complete, validated_at, counts, hard_errors, warnings, unscheduled}`
- `is_valid`: no hard error. `is_complete`: every session the term's teaching assignments require is scheduled (and at least one is required). `validation_passed = is_valid and is_complete`.
- `counts`: `{required_sessions, scheduled_sessions, unscheduled_sessions, scheduled_periods, hard_errors, warnings}` (a 2-period lab is one session and two periods).
- `hard_errors` / `warnings`: `[{code, severity, message, details}]`. Hard codes are those of the clash service (`faculty_clash`, `batch_clash`, `room_clash`, `room_too_small`, `room_unavailable`, `room_type_mismatch`, `slot_is_break`, `slot_inactive`, `lab_not_consecutive`, `faculty_unavailable`, ...) plus `too_many_sessions` and `assignment_outside_term`. Warnings: `outside_preferred_slots` (a preference, never a failure) and `stale_unscheduled_item`.
- `unscheduled`: one row per missing session `{assignment_id, session_no, batch, subject, faculty, reason_code, reason_text}`. The reason is the one stored at generation time; a missing session with no stored item gets `reason_code: "not_scheduled"`.

**What validation changes.** Only `validation_passed`, `validated_at` and, for the two statuses below, `status`: a passing `draft` becomes `validated`; a failing `validated` goes back to `draft`. Approved, published, pending, rejected and archived timetables keep their status (only the flag and timestamp are updated). It never edits entries or unscheduled items and cannot approve or publish.
**Discard rule change.** `DELETE /timetables/:id` now accepts `draft` and `validated` (a validated timetable is still just a draft that passed), so a passing validation does not lock the setup data.

## Planned (by owner)

| Owner | Endpoints |
|---|---|
| Isha | `/faculty` CRUD, `/faculty/:id/availability`, `/faculty/:id/workload`, `/announcements` (+ `/publish`, `/mine`) |
| Diya | `GET /student/timetable`, `POST /import/students` (the other Diya endpoints are implemented above) |
| Pragya | R23 equipment endpoints (optional) |
| Jiya | `PATCH /timetables/:id/entries/:eid`, `/:id/submit|approve|reject|publish`, `/:id/export?format=pdf|xlsx`, `GET /faculty/timetable` |

## In-process service contracts (planned signatures)

| Provider | Function | Used by |
|---|---|---|
| Diya | `get_scheduling_input(term_id, scope) -> SchedulingInput` | Jiya |
| Isha | `get_availability(faculty_id)`, `get_workload(faculty_id, timetable_id)` | Jiya, Pragya |
| Pragya | `check_session(placement, scheduled=None, timetable_id=None, ignore_entry_ids=()) -> list[Conflict]` (`Placement(faculty_id, batch_id, room_id, time_slot_ids, subject_id)`; pass `scheduled` as in-memory `ScheduledPeriod`s and a `PlanningContext` for speed) | Jiya (generator R7, editor R15) |
| Pragya | `validate_timetable(timetable_id) -> ValidationReport` (`.is_valid`, `.hard`, `.advisory`) | Jiya (R10) |
| Pragya | `rank_rooms(subject, batch, time_slot_ids, scheduled=None, timetable_id=None, ignore_entry_ids=()) -> list[Room]` (smallest suitable first); `explain_rooms(...)` returns every room with the reasons it was excluded | Jiya |
| Jiya | `notify_published(timetable)` | Isha (announcements) |
