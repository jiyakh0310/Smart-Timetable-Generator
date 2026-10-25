// R11 / R12 - read-only published timetable for Faculty and Students: API calls and the grid builder.
import { api } from '../../services/api.js';
import { buildQuery } from '../../services/query.js';

export const publishedApi = {
  faculty: (termId) => api.get(`/faculty/timetable${buildQuery({ term_id: termId })}`),
  student: (termId) => api.get(`/student/timetable${buildQuery({ term_id: termId })}`),
};

/*
 * Turns the server's view into the shape WeeklyTimetable expects. Sessions already merge a lab's consecutive periods,
 * so a lab simply spans `periods` rows. `who` decides the second line: a teacher sees the batch, a student sees the teacher.
 */
export function buildPublishedGrid(view, who) {
  const days = [...new Map(view.slots.map((s) => [s.day_of_week, s])).values()].sort((a, b) => a.day_of_week - b.day_of_week)
    .map((s) => ({ key: s.day_of_week, label: s.day_name.slice(0, 3), name: s.day_name }));
  const periods = [...new Map(view.slots.map((s) => [s.period_no, s])).values()].sort((a, b) => a.period_no - b.period_no)
    .map((s) => ({ key: s.period_no, start: s.start_time, end: s.end_time, kind: s.slot_type === 'break' ? 'break' : 'class' }));
  const entries = view.sessions.map((s, i) => ({
    id: `${s.day_of_week}-${s.period_no}-${i}`,
    dayKey: s.day_of_week,
    periodKey: s.period_no,
    span: s.periods,
    title: `${s.subject.code} · ${s.subject.name}`,
    lines: [`Room ${s.room.code}`, who === 'faculty' ? s.batch.name : s.faculty.name],
    kind: s.subject.class_type === 'lab' ? 'lab' : 'theory',
  }));
  return { days, periods, entries };
}
