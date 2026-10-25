# Requirements Mapping

Source of truth: the MoSCoW document (R1-R29), SRS, Planning, Design Tasks and the group's module division. Requirement IDs are preserved. Jiya's test document writes the same IDs as `FR7`, `FR10`, ...; they are identical to `R7`, `R10`, ...

## Requirement to member

| ID | Requirement | MoSCoW | Owner | Milestone | Status |
|---|---|---|---|---|---|
| R1 | Admin/Faculty/Student login with role-based access | Must | Isha | M1 | **Done** |
| R2 | Faculty management | Must | Isha | M3A | **Done** (API + screen + login linkage + tests) |
| R3 | Student and batch management | Must | Diya | M2 | **Done** (batches + students: API, screens, tests) |
| R4 | Subject/course management | Must | Diya | M2 | **Done** (API + screen + tests) |
| R5 | Classroom and laboratory management | Must | Pragya | M4A | **Done** (API + screen + tests) |
| R6 | Time-slot management | Must | Diya | M2 | **Done** (API + screen + tests) |
| R7 | Automated timetable generation | Must | Jiya | M5 | **Done** (term-wide constraint-based generator, Admin API + Timetables screen + tests). Validation workflow (R10), approval and publishing are not built yet |
| R8 | Faculty / batch / classroom clash detection | Must | Pragya | M4A | **Done** as reusable backend checks + API (`clash_service.py`); the generator and editor will call them |
| R9 | Classroom allocation by batch size and room capacity | Must | Pragya | M4A | **Done** as checks + room ranking/suggestion (`rank_rooms`, `/rooms/suggest`); automatic assignment happens inside the generator (R7) |
| R10 | Timetable validation | Must | Jiya | M6 | **Done** (Admin validation endpoint + result panel + tests): hard rules via `validate_timetable`, completeness against the term's assignments, advisory warnings; sets `validation_passed`. Approval/publishing (R16/R11) not built |
| R11 | Admin timetable management and publishing | Must | Jiya | M5 | **Partly done**: the Admin side (generate, validate, edit, approve, publish) and the faculty read-only view of their published classes are built; exports are built (R18) |
| R12 | Students view published timetable (read-only) | Must | Diya | M6 | **Done** (a student sees the current published timetable of their own batch, read-only, server-enforced) |
| R13 | Faculty availability and preferences | Should | Isha | M3A | **Done, Admin-managed** (hard unavailability + soft preferences). Faculty self-service is still planned (M8). |
| R14 | Faculty workload balancing | Should | Isha | M7 | **Done** for generation, validation and the Admin view: `max_weekly_hours` is a hard limit (measured in real teaching hours), workload spread across the week is a soft score. Faculty self-service workload view and `/faculty/:id/workload` are not built |
| R15 | Manual timetable editing with conflict checking | Should | Jiya | M8 | **Done** (Admin moves one session of a draft/validated timetable to another slot and/or room; every hard rule re-checked on the server; the timetable is re-validated on save). Approval/publishing not built |
| R16 | Timetable approval workflow | Should | Jiya | M9 | **Done** (Admin submit / approve / reject-with-reason / publish, each step re-validated on the server; one current published version per term; superseded versions archived). Faculty/student viewing of published timetables is R11/R12 and is not built |
| R17 | Timetable version management | Should | *unowned* (Jiya's module) | M5 | **Partly done**: every generation gets the next version number and is saved as a draft; restore/compare deferred (as agreed) |
| R18 | PDF/Excel timetable export | Should | Jiya | M10 | **Done** (PDF and .xlsx export for Admin, Faculty and Student, server-filtered, with Export PDF / Export Excel controls) |
| R19 | Notifications and announcements | Could | Isha | M9 | Planned |
| R20 | Reports and analytics | Could | unowned | - | Not planned |
| R21 | Audit logs | Could | unowned | - | Not planned |
| R22 | Bulk import (Excel/CSV) | Could | Diya | M9 | Planned |
| R23 | Room equipment-based allocation | Could | Pragya | M9 | Planned |
| R24 | Automatic timetable regeneration | Could | unowned | - | Not planned |
| R25-R29 | Mobile app, ERP integration, AI prediction, attendance, auto substitution | Won't | - | - | Out of scope |

Build order follows MoSCoW priority: all Must items before Should, Should before Could.

## Cross-cutting items without a requirement ID

| Item | Source | Handling |
|---|---|---|
| Admin dashboard | SRS core feature | Shared; M1 shell with real counts, grows each milestone |
| Departments, programs, academic terms | Planning (Academic Setup) | Minimal tables in M1 |
| System settings (max classes/day, max faculty hours) | Planning sketch | `system_settings` table; used by generator in M4 |
| Teaching assignments (faculty x subject x batch x term) | Added by us (SRS `SUBJECT -> Faculty` cannot express per-batch teachers; see conflict 10). Hand sketch: "Faculty Mgmt -> Subject Allocation" | **Done (M3B)**: API + Admin screen. It is the input the generator (R7) consumes. |

## Document conflicts and resolutions

| # | Conflict | Resolution |
|---|---|---|
| 1 | **Department Head / Timetable Coordinator** role appears in SRS, Planning, Design (DFD) and MoSCoW. | **Deliberate scope change (approved):** only Admin, Faculty, Student. The Admin performs review, approval and publication. |
| 2 | R16 approval workflow is *Should*, but the core workflow requires "Admin reviews, approves, publishes". | Core R11 has a minimal status chain (`draft -> validated -> approved -> published`). R16 later adds `pending_approval`, `rejected` with saved reason, and re-submission. |
| 3 | Faculty availability is a hard constraint in the brief, but R13 is *Should*. | The availability table exists from M1; the generator respects availability when data exists. Full R13 UI comes in M8. |
| 4 | Export formats: SRS/Planning say PDF, Excel and CSV; MoSCoW R18 says PDF/Excel. | PDF and Excel only. CSV is accepted for bulk *import* (R22). |
| 5 | Hand-drawn architecture sends "Admin/Faculty" to one dashboard; SRS lists a separate Faculty dashboard. | Separate, read-oriented Faculty portal. |
| 6 | Planning says faculty "view assigned timetable"; SRS says "published timetables". | Faculty see only **published** timetables, limited to their own classes. Students see only their own batch's published timetable (approved decision). |
| 7 | Design documents say "Teacher". | "Faculty" is used everywhere. |
| 8 | Design state diagram #10 (reschedule requests and notifications) has no requirement ID. | Not built. Only R19 announcements. |
| 9 | Hand sketch shows Captcha and Forgot-password; not in SRS or MoSCoW; reset needs email delivery. | Not built. Provided instead: change own password. |
| 10 | SRS `SUBJECT` has a single Faculty, which cannot express different teachers per batch. | Added `teaching_assignments` (term, batch, subject, faculty, sessions/week). |
| 11 | Lab duration unspecified. | Lab sessions use consecutive periods, default 2, configurable per subject (`lab_block_periods`). Approved. |
| 12 | Test case IDs (TC01...) repeat across members' documents. | Prefixed: `ISH-TC01`, `DIY-TC01`, `PRA-TC01`, `JIY-TC01`. |
| 13 | R17 has no owner. | A new version number per generation (approved); restore/compare deferred. |
