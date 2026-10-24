# Testing Plan

Backend: `pytest` (in `backend/app/tests/<member>/`), in-memory SQLite so the real MySQL is untouched. Frontend: production build check. Test IDs are prefixed per member (`ISH-`, `DIY-`, `PRA-`, `JIY-`) because the members' documents reuse TC01...

## Milestone 1 - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **30 passed** |
| `npm run build` | succeeded |
| `flask db upgrade` on SQLite, then `seed-demo`, then `flask db check` | upgrade ok, seed ok, "No new upgrade operations detected" |
| `flask db upgrade --sql` with a MySQL URL (offline) | MySQL DDL generated for all 20 tables plus Alembic's version table; longest constraint name 55 chars (< 64) |
| HTTP checks through Vite proxy to Flask (SQLite) | health ok; wrong password 401; blank fields 400; admin summary 200; student/faculty 403; no token 401 |
| **Real MySQL** (`flask db upgrade`, login against MySQL) | **Not run by the assistant** - needs your credentials; you run the README steps |
| **Visual check of the UI in a browser** | **Not done** - build/HTTP only |

### Covered by the 30 tests
- Isha R1: ISH-TC01 valid login; ISH-TC02 wrong password; ISH-TC03 blank fields; ISH-TC04 student denied admin API (403)
- Extras: unknown email same message as wrong password; faculty denied; missing token 401; garbage token 401; disabled account cannot log in; token stops working when the account is disabled; case-insensitive email; role-specific `/me`; change-password rules; passwords stored hashed; JSON error envelope on 404
- Shared: health endpoint; seed idempotent; unique email; capacity > 0 and slot start < end enforced; database blocks faculty / room / batch double-booking; same resources in different slots allowed; config rejects placeholder/short secrets and placeholder DB settings; MySQL URL built safely from special-character passwords

## Acceptance criteria for later milestones

| M | Must demonstrate | Test IDs |
|---|---|---|
| M2 | CRUD with validation; delete blocked when referenced; invalid time range rejected | ISH-TC05-08, DIY-TC01-12 |
| M3 | Clash detection; back-to-back slots allowed; labs only in labs; "no room" reported not forced | PRA-TC01-18 |
| M4 | Seeded data generates a timetable that validates with 0 conflicts; impossible data yields explained unscheduled items | JIY-TC01-08 |
| M5 | Publishing blocked on clashes; clashing manual edit rejected and not saved | JIY-TC09-16 |
| M6 | Student sees only own batch's published timetable; faculty only own classes; drafts invisible | DIY (R12) |
| M7 | PDF/Excel export; empty timetable no error; unauthorized 403 | JIY-TC21-24 |
| M8 | Availability, workload, approval workflow with reject reason | ISH-TC09-16, JIY-TC17-20 |
| M9 | Announcements, bulk import, equipment allocation | ISH-TC17-20, DIY-TC13-16, PRA-TC19-24 |
| M10 | Full test run, README verified on a clean machine | - |

## Milestone 2A (UI redesign) - results (actually executed)

| Check | Result |
|---|---|
| `npm test` (Vitest + Testing Library, jsdom) | **43 passed** in 8 files |
| `npm run build` | succeeded (CSS 25.7 kB, JS 199 kB, gzip 5.7 / 63.9 kB) |
| `python -m pytest` (backend, unchanged) | **30 passed** |
| Dev server: all 5 CSS files, `main.jsx`, `App.jsx`, shell, admin dashboard, timetable component compile | HTTP 200, no Vite errors |
| Real MySQL (`smart_timetable_m1`) through the Vite proxy: health, admin login, admin summary | OK |
| WCAG contrast computed for 21 token pairs | all pass after raising the input border to 3.7:1 (it was 1.5:1) |
| **Visual / responsive check in a real browser, keyboard walk-through, screen reader** | **Not done by the assistant - manual testing required** |

Frontend tests cover: weekly timetable (grid placement, 2-period lab row-span, day tabs, wrap-around navigation, read-only, no invented data), confirm dialog (modal semantics, focus, Tab trap, Escape, focus return), protected routes (signed out, wrong role, loading), login form (ISH-TC01..03 behaviours), app shell (role-specific nav, grouped admin nav, sign-out confirmation, menu Escape), nav config (exactly three roles, no Department Head, unbuilt items always name owner/requirement/milestone), and page smoke tests (real API numbers shown, error state, no console errors, one `h1`, "Not available yet" labels, student has no buttons).

## Milestone 2: Time slots (R6) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **99 passed** (30 from M1, 2 new config/password-hash tests, 67 time-slot API cases including parametrised ones; ~30 s) |
| `npm test` | **84 passed** in 12 files |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run of the live API: list/search/filter, create, duplicate, overlap, back-to-back, end-before-start, all-or-nothing multi-day, PATCH, student 403/200, no token 401 | **16/16 passed**; the script created only Sunday rows and removed them (35 -> 35 rows) |
| Browser walk-through of the Time Slots screen | **Not done by the assistant - manual testing required** |

Backend tests cover: Admin-only writes (student and faculty get 403, anonymous 401, every signed-in role can read); DIY-TC09 create, DIY-TC10 end before start, DIY-TC11 update, DIY-TC12 working days and a break; validation of every field; unknown fields; duplicate period; overlap; back-to-back allowed; period/time order; all-or-nothing multi-day create; pagination, filters and search; bad query parameters; delete of an unused slot; delete refused when a timetable or faculty availability uses the slot (and the availability row survives); a used slot can still be disabled but not moved.
Frontend tests cover: `useListQuery` (debounce, filters, stale responses, errors, page step-back), `DataTable` states, `Pagination`, the Time Slots screen (listing, filters, search, empty/error/retry, create validation and success, server conflict shown on the form, edit prefill and locked fields, delete confirmation, in-use delete offering "disable"), and routing (built screen vs "not available yet", student redirected).
Test speed: the testing config uses a cheap password hash (`pbkdf2:sha256:1000`); a test pins that development/production still use scrypt.

## Milestone 2B: Subjects (R4) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **177 passed** (99 earlier + 78 subject API cases) |
| `npm test` | **115 passed** in 13 files, run twice with no flakiness |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run of the live subjects API (23 checks: list/search/filter, create, case-insensitive duplicate on MySQL collation, lab defaults, validation, update, in-use lock and delete refusal on seeded CS301, student 403/200, 401) | **23/23 passed**; only `ZZ9xx` rows were created and they were removed (6 -> 6 subjects; the 12 teaching assignments untouched) |
| Browser walk-through of the Subjects screen | **Not done by the assistant - manual testing required** |

Backend tests cover: Admin-only writes (403 for student/faculty, 401 anonymous, all roles can read); paging, ordering, every filter, case-insensitive search, literal `%`/`_`, bad query values; DIY-TC05 create, DIY-TC06 update, DIY-TC07 missing code, DIY-TC08 theory/lab; code normalisation; ~20 invalid-value cases; unknown fields; duplicate code (also differing in case/spaces); lab/theory room rules; lab hours vs session length; type switching defaults; scheduling fields locked when assigned (while name/credits/room stay editable, and unchanged values re-sent by the form are accepted); delete refused for assigned subjects with nothing cascaded away, message mentions timetable entries; delete of an unused subject and code reuse.
Frontend tests cover: listing with badges and usage, all filters and search, empty/error/retry, create validation (every required field, bad code, lab hours rule), valid theory and lab payloads, type switching, server duplicate error on the field, edit prefill and locked fields, delete confirmation / in-use notice / refused delete toast, plus unit tests of the form rules.

## Milestone 2C: Batches and Students (R3) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **285 passed** (177 earlier + 108 new) |
| `npm test` | **171 passed** in 15 files |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run of the live APIs (27 checks: batch rules, case-insensitive duplicates on the MySQL collation, capacity and strength accuracy, moving students between batches, seeded-batch protections, privacy 403s, delete -> login disabled using a throwaway user) | **27/27 passed**; every temporary record removed (batches 2, students 4, assignments 12, users 11 before and after) |
| Browser walk-through of the Batches and Students screens | **Not done by the assistant - manual testing required** |

Backend tests cover: batches - permissions, listing/paging/filters/search, create (DIY-TC04, generated name, department from program, semester bound, ~18 invalid values, duplicates by section and name), update, **strength accuracy** (cannot drop below enrolled, equal is allowed, counts follow real records), scheduled-batch locks, delete refusal for students / assignments / announcements / timetable entries; students - **admin-only including reads (403 for faculty and students, nothing leaked)**, listing/paging/filters/search, create (DIY-TC01, TC03), normalisation, optional email, invalid values, unknown fields (including `user_id`), duplicate number/email, **capacity** (full batch rejected, raise strength then ok, move updates both counts, move into a full batch refused, old over-full data still editable), update (DIY-TC02), delete (login disabled, token stops working, other accounts unaffected, number reusable).
Frontend tests cover: both screens' listing, filters, search, empty/error/retry; create/edit validation (client side and server errors shown on fields); semester bounded by program; strength cannot go below enrolled; locked fields; full batches disabled in the student form while the student's own batch stays selectable; delete confirmations including the login-disabled warning and the in-use notice; routing (new screens built, old combined nav item gone, students redirected away from admin pages).

## Milestone 3A: Faculty and availability (R2, R13) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **375 passed** (285 earlier + 90 new) |
| `npm test` | **239 passed** in 18 files (171 earlier + 68 new) |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run of the live APIs (31 checks: create with linked login and hashed password, case-insensitive duplicates on the MySQL collation, role/user_id injection refused, reset password, deactivation blocks login and existing tokens, availability hard/soft on real rows, break/unknown/duplicate slots refused, disabled slot keeps its row, slot with availability cannot be deleted, seeded F001 protected, 403/401, cleanup) | **31/31 passed**; temporary faculty, its login and availability removed, the toggled time slot restored (faculty 6, users 11, availability 0, assignments 12 before and after) |
| Browser walk-through of the Faculty and Availability screens | **Not done by the assistant - manual testing required** |

Backend tests cover: every endpoint Admin-only including reads (faculty and students get 403, a faculty member cannot edit their own record); listing, paging, filters, search; create with linked faculty-role login (ISH-TC05), hashed password never returned, new account can sign in and cannot reach admin or student data; role / user_id / is_active injection refused with nothing half-created; normalisation; ~13 invalid values; weak and identical-to-identity passwords; duplicate code and email (also against admin and student accounts); update (ISH-TC06), keep-own-values, role/login link immutable; deactivate and reactivate (login and live token); reset password; delete of unused faculty removes the login, delete refused for assignments and timetable entries; availability view (all 35 slots, defaults), save hard and soft (ISH-TC09), update (ISH-TC10), morning preferences (ISH-TC11), invalid input (ISH-TC12), duplicates, unknown / break / disabled slots, atomic failure, per-faculty isolation, preservation for disabled slots, slot-delete protection, and cascade only for the deleted faculty member.
Frontend tests cover: faculty list, filters, search, empty/error; create validation and weak-password cases, show/generate password (14 characters, policy-compliant, no look-alikes, always different, uses the secure random source), payload never contains a role, server duplicate error on the field; edit prefill and active flag; reset-password dialog; delete / deactivate / already-inactive flows; the availability grid (labels in words, keyboard operation, cycling, counts, unsaved changes, save payload excludes disabled slots and breaks, discard, clear, server error, switching faculty with a confirmation, empty and error states); routing (built screens, students and faculty redirected away from admin pages).

## Milestone 3B: Teaching assignments - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **442 passed** (375 earlier + 67 new) |
| `npm test` | **264 passed** in 20 files (239 earlier + 25 new, plus routing assertions added to existing tests) |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run of the live API (20 checks: seeded data has no drift, computed lab sessions, MySQL-stored value, client-sent count refused, duplicate / semester-mismatch / unknown references refused, soft preference vs hard unavailability warnings, assignment never blocked by availability, protections on seeded subject/faculty unchanged, 403/401, cleanup) | **20/20 passed**; temporary subjects, faculty and assignment removed (assignments 12, subjects 6, faculty 6, users 11, availability 0 before and after) |
| Browser walk-through of the Teaching assignments screen | **Not done by the assistant - manual testing required** |

Backend tests cover: Admin-only including reads (403 for faculty and students, `/terms` readable by any signed-in user); listing, paging, ordering, every filter, search, bad query values; **computed session counts** (theory, 3-period lab, singular lab) and refusal of a client-sent count; all four references invalid (20 cases); same-semester rule, cross-department flagging, inactive faculty, inactive term, one-teacher-per-subject duplicates and the same subject on another batch; update (teacher, subject change recomputes sessions, unchanged re-send, inactive-but-unchanged teacher, duplicate on move); **frozen assignments** for both timetable entries and unscheduled items (every change refused, nothing altered, lock reported before duplicates, delete refused); delete, and the unlocking of subject / faculty after removal; existing seeded-data protections; **availability warnings** (shortfall counted across all of a faculty member's assignments, soft preference never counted, a break does not connect two periods for a lab, warnings clear when availability is cleared, assignments never blocked).
Frontend tests cover: the weekly-requirement wording (theory, lab, singular, invalid lab hours) and form rules; listing with badges and warning flags; batch / faculty / type filters and search; empty and error states; the add form (active term preselected, subjects limited to the batch's semester, changing batch clears an incompatible subject, calculated need shown read-only, validation, payload of only four ids, availability warnings surfaced as a notice, duplicate error on the field); edit (prefill, warnings, frozen fields); delete (confirmation, in-timetable refusal without an API call, failure toast); routing (screen built, students and faculty redirected).

## Milestone 4A: Rooms & labs, clash and allocation checks (R5, R8, R9) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **607 passed** (442 earlier + 165 new) |
| `npm test` | **297 passed** in 21 files (264 earlier + 33 new; a few older tests were updated because Rooms is no longer an "unbuilt" example) |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) smoke run (31 checks, including true `TIME` interval overlap between different slot rows, the touching 10:00 boundary, capacity equal/one-short, lab consecutive periods across the lunch break, hard vs soft availability through the real API, saved-timetable validation reporting an overlap once, scheduled-room locks, room suggestions, 403/401) | **31/31 passed**; throwaway room, timetable, entries and test slots removed and every table count restored (rooms 7, slots 35, timetables 0, entries 0, availability 0, users 11) |
| Browser walk-through of the Rooms & labs screen | **Not done by the assistant - manual testing required** |

Backend tests cover: rooms - Admin-only, listing / filters / search, create (PRA-TC01, TC02), validation (PRA-TC05, TC06 incl. capacity 0 / negative / 2001 / non-integer), duplicates (also differing in case), update (PRA-TC03), lab-type rules, **scheduled-room locks** (no delete, type locked, capacity floor with equal allowed, out-of-service allowed with a message); clash service - the **overlap definition** (same slot, touching, different day, partial overlap, one minute short of touching, starting exactly at the end), faculty / batch / room clashes alone and together (PRA-TC07..TC09), **back-to-back and other-day classes do not clash** (TC10), true overlap between different slot rows (TC11), moving an entry with `ignore_entry_ids` (TC12), in-memory `scheduled` input; capacity (equal allowed, one short rejected), out-of-service rooms, lab vs classroom vs theory-in-lab and a subject's required type (TC13, TC14, TC16); break / disabled / unknown / duplicate slots; lab sessions - consecutive periods valid (including after the break), order-independent, split across the break rejected, gaps and two days rejected, wrong length, 3-period labs; **hard unavailability vs soft preference** (hard blocks, preference gives only an advisory and `ok` stays true); `rank_rooms` / `explain_rooms` (smallest first, busy and out-of-service rooms drop out, no suitable room gives an empty list, every exclusion has a reason); `validate_timetable` (clean, empty, unknown, an overlap reported once, problems that appear after saving, advisory-only stays valid, theory in a lab, 8 lab-run shapes); the three HTTP endpoints (permissions, input validation, `assignment_id` derivation and contradiction, checks never modify data, validate and suggest responses).
Frontend tests cover: Rooms listing, four filters and search, empty/error; the add form (focus, lab type only for laboratories, required fields, capacity 0 / -5 / 2001 / 40.5 rejected before sending, classroom and laboratory payloads, duplicate code from the server); edit (prefill, scheduled room: type locked, capacity floor with equal allowed, warning before taking a scheduled room out of service, server refusal); delete (confirmation, in-use explanation with no API call, failure toast); form-rule unit tests; routing (screen built, students and faculty redirected).

## Milestone 5: Timetable generation (R7) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **655 passed** (607 earlier + 48 new in `tests/jiya/test_generation.py`) |
| `npm test` | **320 passed** in 22 files (297 earlier + 20 new Timetables tests + 3 routing tests; older tests that used Timetables as the "unbuilt" example now use Announcements) |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) generation smoke (23 checks) | **23/23 passed**: 32 sessions / 36 periods scheduled as draft v1; the existing validator reports 0 hard conflicts; an independent SQL self-join on real `TIME` columns finds 0 faculty/batch/room overlaps; capacity, room type, break/disabled slots and 2-consecutive-period labs verified in SQL; repeat = v2 with identical placements and no duplicates; hard unavailability honoured; insufficient slots give a partial result with stored reasons; **two simultaneous generations received distinct versions with 36 entries each**; list/detail; assignment frozen (409); approved timetable not discardable; 403/401; 6 drafts discarded; every table count and slot flag restored (timetables 0, entries 0, unscheduled 0) |
| Earlier real-MySQL rooms/clash smoke re-run | **31/31 passed** |
| Browser walk-through of the Timetables screen | **Not done by the assistant - manual testing required** |

Backend tests cover: success for theory + labs (counts per assignment, passes the existing validator, no overlaps proven independently, capacity and room-type rules, labs = consecutive periods in one lab, determinism); overlapping slot records (real clock time); hard unavailability (partial and total, reasons name the person); capacity too small everywhere and no laboratory in service (reported, never forced); a subject's required room type; labs with no consecutive window; breaks/disabled slots never used; inactive faculty; insufficient slots (every session accounted for, reasons meaningful, none silently dropped); preferences only soft (placement never blocked, preferred slot used when free, warning); versions (1,2,3, no duplicates, earlier versions untouched), a lost version race retried and a persistent one saving nothing; rollback (hard conflict caught by the validator, planner crash, validator crash after rows were flushed); endpoints (generate, list/filter, detail, unscheduled reasons, validation, unknown fields, inactive term, no assignments, 404); permissions (401, 403 for faculty and student on every endpoint, nothing created); discard (frees the setup data, only drafts, other versions kept); regressions (setup data unchanged, assignments frozen after generation).
Frontend tests cover: listing/empty/error, drafts-only discard button, the generate dialog (active terms only, preselection, real summary with reasons and warnings, server refusal, no active term), detail (batch grid with breaks, lab spanning two rows, disabled days hidden, batch switch, unscheduled table with reasons, all-scheduled message, back, load error), discard confirm/cancel/refusal, and the grid helper functions.

## Milestone 6: Timetable validation (R10) - results (actually executed)

| Check | Result |
|---|---|
| `python -m pytest` | **697 passed** (655 earlier + 42 new in `tests/jiya/test_validation.py`) |
| `npm test` | **332 passed** in 23 files (320 earlier + 12 new in `TimetableValidation.test.jsx`) |
| `npm run build` | succeeded |
| Real MySQL (`smart_timetable_m1`) validation smoke (18 checks) | **18/18 passed**: complete timetable passes and is recorded; repeat gives the same report; a client-supplied "valid" body is ignored; room out of service + hard unavailability fail and reset the flag and status; the overlap between two different slot rows is caught on real `TIME` data; a missing session is reported as `not_scheduled`; a partial generation keeps its stored reasons; preference-only passes with warnings; an approved timetable stays approved; no publish/approve endpoint; 403/401/404; validated drafts can be discarded; every table, room and slot flag restored (timetables 0, entries 0) |
| Earlier MySQL smokes re-run | generation **23/23**, rooms/clash **31/31** |
| Browser walk-through of the Validate action | **Not done by the assistant - manual testing required** |

Backend tests cover: a valid complete timetable (recorded, counts, list/detail show it, entries untouched, request body ignored); each hard conflict on saved rows - faculty, batch and room overlap through a second slot row, room too small, room out of service, theory in a lab and lab in a classroom, disabled slot, break slot, lab session cut short, lab periods split apart, hard unavailability - each leaving `validation_passed` false and status draft, plus equality with the existing validator; completeness - partial generation, a missing session with and without a stored reason, a missing lab session, a stale unscheduled item (warning only), too many sessions, an empty timetable; preferences produce warnings only; repeat validation, status moving both ways, a stale `validation_passed = true` being reset by a failing run, a crashing validator changing nothing, other versions untouched; never approves/publishes (every other status is kept, `published_at`/`approved_by` stay empty, no publish/approve route, a validated timetable can still be discarded); 401, 403 for faculty and student, 404.
Frontend tests cover: not-validated notice and keyboard-reachable button, the recorded state in the list, the pass, the failure with hard errors / warnings / counts / each missing session with its reason, incomplete-only, warnings-only pass, loading and disabled button, server error with retry, focus moving to the result, discard still available after a pass and absent for an approved timetable.

## Known limitations of M1
- JWT is stateless: "Sign out" removes the token in the browser; a stolen token stays valid until it expires (default 8 h).
- No login rate-limiting or account lockout yet.
- Token is kept in `localStorage` (acceptable for a college project; a cookie-based session would resist XSS better).
