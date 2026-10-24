// Jiya - R7 timetable generation: API calls and the helpers that turn a saved timetable into a weekly grid.
import { api } from '../../services/api.js';

export const TIMETABLES_PATH = '/timetables';
export const timetablesApi = {
  generate: (termId) => api.post('/timetables/generate', { term_id: termId }),
  get: (id) => api.get(`/timetables/${id}`),
  workloadPreview: (termId) => api.get(`/timetables/workload-preview?term_id=${termId}`),
  validate: (id) => api.post(`/timetables/${id}/validate`, {}),
  discard: (id) => api.delete(`/timetables/${id}`),
  terms: () => api.get('/terms'),
  slots: () => api.get('/time-slots?per_page=100'),
};

export const GENERATION_STATUS = {
  complete: { tone: 'success', label: 'Complete', text: 'Every required session was scheduled.' },
  partial: { tone: 'warning', label: 'Partly scheduled', text: 'Some sessions could not be placed. They are listed with the reason.' },
  none_scheduled: { tone: 'danger', label: 'Nothing scheduled', text: 'No session could be placed. Check the reasons below.' },
};

export const REASON_LABEL = {
  faculty_unavailable: 'Faculty unavailable',
  faculty_inactive: 'Faculty not active',
  faculty_busy: 'Faculty already teaching',
  batch_busy: 'Batch already in class',
  rooms_busy: 'No free room',
  no_suitable_room: 'No suitable room',
  no_consecutive_window: 'No consecutive periods',
  no_class_slots: 'No class periods',
  no_free_slot: 'No free period',
  not_scheduled: 'Not scheduled',
  workload_limit: 'Weekly hour limit',
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
export { plural };

/*
 * Weekly grid for one batch. `slots` come from /time-slots (so breaks and empty periods show); only active slots are used.
 * Returns { days, periods, entries } in the shape WeeklyTimetable expects. A lab's consecutive periods become one 2-row entry.
 */
export function buildGrid(slots, entries, batchId) {
  const usable = slots.filter((s) => s.is_active);
  const days = [...new Map(usable.map((s) => [s.day_of_week, s])).values()]
    .sort((a, b) => a.day_of_week - b.day_of_week)
    .map((s) => ({ key: s.day_of_week, label: s.day_name.slice(0, 3), name: s.day_name }));
  const periods = [...new Map(usable.map((s) => [s.period_no, s])).values()]
    .sort((a, b) => a.period_no - b.period_no)
    .map((s) => ({ key: s.period_no, start: s.start_time, end: s.end_time, kind: s.slot_type === 'break' ? 'break' : 'class' }));

  const mine = entries
    .filter((e) => e.batch.id === batchId)
    .sort((a, b) => a.time_slot.day_of_week - b.time_slot.day_of_week || a.time_slot.period_no - b.time_slot.period_no);
  const cells = [];
  mine.forEach((e) => {
    const prev = cells[cells.length - 1];
    const joins = prev && prev.assignmentId === e.assignment_id && prev.dayKey === e.time_slot.day_of_week && prev.lastPeriod + 1 === e.time_slot.period_no && e.subject.class_type === 'lab';
    if (joins) {
      prev.span += 1;
      prev.lastPeriod = e.time_slot.period_no;
      return;
    }
    cells.push({
      id: e.id,
      assignmentId: e.assignment_id,
      dayKey: e.time_slot.day_of_week,
      periodKey: e.time_slot.period_no,
      lastPeriod: e.time_slot.period_no,
      span: 1,
      title: `${e.subject.code} · ${e.subject.name}`,
      lines: [e.faculty.name, `Room ${e.room.code}`],
      kind: e.subject.class_type === 'lab' ? 'lab' : 'theory',
    });
  });
  return { days, periods, entries: cells.map(({ assignmentId, lastPeriod, ...cell }) => cell) };
}

export function batchesIn(timetable) {
  const seen = new Map();
  timetable.entries.forEach((e) => seen.set(e.batch.id, e.batch.name));
  timetable.unscheduled.forEach((u) => seen.set(u.batch.id, u.batch.name));
  return [...seen].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
}

// What the last validation run recorded on the timetable itself.
export function validationState(t) {
  if (t.validation_passed) return { tone: 'success', label: 'Validation passed' };
  if (t.validated_at) return { tone: 'danger', label: 'Validation failed' };
  return { tone: 'neutral', label: 'Not validated' };
}
