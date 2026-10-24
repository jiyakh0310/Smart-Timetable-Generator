"""Member-owned feature modules. Each member registers their blueprint(s) here."""
from app.common import dashboard
from app.modules.diya import assignment_routes, batch_routes, student_routes, subject_routes, time_slot_routes
from app.modules.isha import faculty_routes, routes as isha_routes
from app.modules.jiya import timetable_routes
from app.modules.pragya import clash_routes, room_routes


def register_blueprints(app):
    app.register_blueprint(isha_routes.bp)      # Isha  - /api/v1/auth
    app.register_blueprint(faculty_routes.bp)   # Isha  - /api/v1/faculty (R2, R13), admin only
    app.register_blueprint(dashboard.bp)        # shared - /api/v1/admin/summary
    app.register_blueprint(time_slot_routes.bp) # Diya  - /api/v1/time-slots (R6)
    app.register_blueprint(subject_routes.bp)   # Diya  - /api/v1/subjects (R4)
    app.register_blueprint(subject_routes.departments_bp)  # lookup for forms
    app.register_blueprint(batch_routes.bp)     # Diya  - /api/v1/batches (R3)
    app.register_blueprint(batch_routes.programs_bp)  # lookup for forms
    app.register_blueprint(student_routes.bp)   # Diya  - /api/v1/students (R3, admin only)
    app.register_blueprint(assignment_routes.bp)  # Diya - /api/v1/teaching-assignments (admin only)
    app.register_blueprint(assignment_routes.terms_bp)  # lookup for forms
    app.register_blueprint(room_routes.bp)      # Pragya - /api/v1/rooms (R5, R9 suggest), admin only
    app.register_blueprint(clash_routes.bp)     # Pragya - /api/v1/conflicts (R8/R9), admin only
    app.register_blueprint(timetable_routes.bp) # Jiya  - /api/v1/timetables (R7 generate, list, detail, discard draft), admin only
    # next: jiya (validation workflow R10, approval, publishing)
    # M3: pragya (rooms, conflicts)   M4+: jiya (timetables)
