"""Jiya - R18 PDF / Excel export: decides WHAT may be exported, builds a neutral Document, hands it to `export_render`.

WHO MAY EXPORT WHAT
  * Faculty / Student: exactly what their read-only view shows (R11 / R12). The document is built from the SAME
    `published_service` view the screens use, so the access rules, the term logic and the "current published version" rule
    live in one place and are not repeated here. Identity comes from the token only; every identity / batch / timetable
    parameter is refused with 400. No published timetable for the term means 404 (no file), never an empty draft.
  * Admin: any saved timetable by id (the same audience as `GET /timetables/:id`), whatever its status. Non-published
    documents say so in their header ("Draft - not published") so a printout can never be mistaken for the live timetable.
  * Documents never contain account emails, ids or validation internals.
"""
import re

from flask import Response

from app.common.errors import AppError
from app.extensions import db
from app.models import TimetableEntry, UnscheduledItem
from app.modules.jiya import export_render, published_service as published
from app.modules.jiya import timetable_service as service

FORMATS = {
    "pdf": ("application/pdf", "pdf"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
}


def parse_format(args) -> str:
    fmt = (args.get("format") or "").strip().lower()
    if fmt not in FORMATS:
        raise AppError("validation_error", "Choose an export format: pdf or xlsx.", 400, {"format": "Must be pdf or xlsx."})
    return fmt


def reject_unknown_params(args, allowed: set) -> None:
    extra = sorted(set(args) - allowed)
    if extra:
        raise AppError("validation_error", "This export does not accept " + ", ".join(extra) + ".", 400, {k: "Not allowed." for k in extra})


def slug(*parts) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(str(p) for p in parts if p))).strip("-") or "timetable"


def render(doc: export_render.Document, fmt: str) -> bytes:
    return export_render.render_pdf(doc) if fmt == "pdf" else export_render.render_xlsx(doc)


def file_response(doc: export_render.Document, fmt: str, filename: str) -> Response:
    mime, ext = FORMATS[fmt]
    response = Response(render(doc, fmt), mimetype=mime)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}.{ext}"'
    response.headers["Cache-Control"] = "no-store"          # personal timetable data: never cached by a shared proxy
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _published_line(view: dict) -> str:
    t = view["timetable"]
    when = f", published {t['published_at'][:10]}" if t.get("published_at") else ""
    return f"Term: {view['term']['name']} ({view['term']['academic_year']}) · Version {t['version']}{when}"


def _require_published(view: dict, term_arg) -> dict:
    if view["timetable"] is not None:
        return view
    if view["term"] is None:
        raise AppError("term_not_found" if term_arg else "no_active_term", "That term does not exist." if term_arg else "There is no active term, so there is nothing to export.", 404)
    raise AppError("no_published_timetable", f"No timetable has been published for {view['term']['name']} yet, so there is nothing to export.", 404, {"term": view["term"]["name"]})


# ---------- faculty / student ----------
def faculty_export(user, args) -> Response:
    reject_unknown_params(args, {"term_id", "format"})
    fmt = parse_format(args)
    view = _require_published(published.faculty_view(user, args, extra_allowed={"format"}), args.get("term_id"))
    who = view["owner"]
    doc = export_render.Document(
        title="My teaching timetable",
        lines=[f"Teacher: {who['name']} ({who['employee_code']})", _published_line(view)],
        slots=view["slots"],
        sections=[export_render.Section("Weekly timetable", view["sessions"], None if view["sessions"] else "You have no classes in this timetable.")],
        footer=f"{who['name']} · {view['term']['name']} · version {view['timetable']['version']}",
    )
    return file_response(doc, fmt, slug("timetable-faculty", who["employee_code"], view["term"]["name"], f"v{view['timetable']['version']}"))


def student_export(user, args) -> Response:
    reject_unknown_params(args, {"term_id", "format"})
    fmt = parse_format(args)
    view = _require_published(published.student_view(user, args, extra_allowed={"format"}), args.get("term_id"))
    who = view["owner"]
    doc = export_render.Document(
        title="Class timetable",
        lines=[f"Student: {who['name']}", f"Batch: {who['batch']}", _published_line(view)],
        slots=view["slots"],
        sections=[export_render.Section(who["batch"], view["sessions"], None if view["sessions"] else "No classes are scheduled for your batch in this timetable.")],
        footer=f"{who['batch']} · {view['term']['name']} · version {view['timetable']['version']}",
    )
    return file_response(doc, fmt, slug("timetable", who["batch"], view["term"]["name"], f"v{view['timetable']['version']}"))


# ---------- admin ----------
def admin_export(timetable_id: int, args) -> Response:
    reject_unknown_params(args, {"format"})
    fmt = parse_format(args)
    timetable = service.get_or_404(timetable_id)
    entries = db.session.scalars(db.select(TimetableEntry).where(TimetableEntry.timetable_id == timetable.id).order_by(TimetableEntry.batch_id, TimetableEntry.time_slot_id)).unique().all()
    by_batch: dict = {}
    for e in entries:
        by_batch.setdefault(e.batch.name, []).append(e)
    sections = [export_render.Section(name, published._sessions(rows, "student")) for name, rows in sorted(by_batch.items())]
    if not sections:
        sections = [export_render.Section("Timetable", [], "No classes are scheduled in this timetable.")]

    status = timetable.status.value.replace("_", " ")
    is_live = timetable.status.value == "published"
    lines = [f"Term: {timetable.term.name} ({timetable.term.academic_year}) · Version {timetable.version}",
             f"Status: {status.capitalize()}" + ("" if is_live else " - NOT the published timetable")]
    items = db.session.scalars(db.select(UnscheduledItem).where(UnscheduledItem.timetable_id == timetable.id).order_by(UnscheduledItem.assignment_id, UnscheduledItem.session_no)).unique().all()
    extra = []
    if items:
        extra.append(("Unscheduled sessions", ["Batch", "Subject", "Teacher", "Reason"], [[i.assignment.batch.name, f"{i.assignment.subject.code} · {i.assignment.subject.name}", i.assignment.faculty.user.full_name, i.reason_text] for i in items]))
    doc = export_render.Document(title=f"Timetable - {timetable.name}", lines=lines, slots=published.week_slots(), sections=sections, footer=f"{timetable.name} · {status}", extra_tables=extra)
    return file_response(doc, fmt, slug("timetable", timetable.term.name, f"v{timetable.version}", "" if is_live else timetable.status.value))
