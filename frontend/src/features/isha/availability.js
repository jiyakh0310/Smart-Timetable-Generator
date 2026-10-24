// Isha - R13 Faculty availability (Admin-managed): API calls and grid logic.
//
// available   = default, nothing stored
// unavailable = HARD: the generator must never schedule the faculty member in that slot
// preferred   = SOFT: favoured when possible, never required
import { api } from '../../services/api.js';

export const availabilityApi = {
  get: (facultyId) => api.get(`/faculty/${facultyId}/availability`),
  save: (facultyId, entries) => api.put(`/faculty/${facultyId}/availability`, { entries }),
};

export const STATUS_CYCLE = ['available', 'unavailable', 'preferred'];
export const STATUS_LABEL = { available: 'Available', unavailable: 'Unavailable', preferred: 'Preferred' };
export const nextStatus = (status) => STATUS_CYCLE[(STATUS_CYCLE.indexOf(status) + 1) % STATUS_CYCLE.length];

// Only active class periods can be configured (breaks and disabled slots are shown but locked).
export const isEditable = (slot) => slot.slot_type === 'class' && slot.is_active;

// Turn the flat slot list into rows (periods) x columns (days). Cells are looked up by "day:period".
export function buildGrid(slots) {
  const days = [...new Map(slots.map((s) => [s.day_of_week, s.day_name])).entries()].sort((a, b) => a[0] - b[0]).map(([day_of_week, day_name]) => ({ day_of_week, day_name }));
  const periodNos = [...new Set(slots.map((s) => s.period_no))].sort((a, b) => a - b);
  const cells = new Map(slots.map((s) => [`${s.day_of_week}:${s.period_no}`, s]));
  const periods = periodNos.map((period_no) => {
    const sample = slots.find((s) => s.period_no === period_no);
    return { period_no, start_time: sample.start_time, end_time: sample.end_time };
  });
  return { days, periods, cell: (day, period) => cells.get(`${day}:${period}`) };
}

export const statusMapOf = (slots) => Object.fromEntries(slots.map((s) => [s.time_slot_id, s.status]));

export function toEntries(slots, statuses) {
  return slots.filter(isEditable).filter((s) => statuses[s.time_slot_id] !== 'available').map((s) => ({ time_slot_id: s.time_slot_id, status: statuses[s.time_slot_id] }));
}

export const isDirty = (slots, saved, local) => slots.filter(isEditable).some((s) => saved[s.time_slot_id] !== local[s.time_slot_id]);

export function countStatuses(slots, statuses) {
  const editable = slots.filter(isEditable);
  return {
    unavailable: editable.filter((s) => statuses[s.time_slot_id] === 'unavailable').length,
    preferred: editable.filter((s) => statuses[s.time_slot_id] === 'preferred').length,
  };
}
