// Teaching assignments: API calls, the weekly-requirement wording and the form rules.
import { api } from '../../services/api.js';

export const ASSIGNMENTS_PATH = '/teaching-assignments';
export const assignmentsApi = {
  create: (body) => api.post('/teaching-assignments', body),
  update: (id, body) => api.patch(`/teaching-assignments/${id}`, body),
  remove: (id) => api.delete(`/teaching-assignments/${id}`),
};

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

// Mirrors the server rule. Theory: one period per hour. Lab: hours / session length sessions of that many CONSECUTIVE periods.
export function weeklyNeed(subject) {
  if (!subject) return null;
  const length = subject.class_type === 'lab' ? subject.lab_block_periods : 1;
  const sessions = Math.floor(subject.weekly_hours / length);
  const periods = sessions * length;
  const valid = subject.class_type !== 'lab' || subject.weekly_hours % length === 0;
  return {
    valid,
    sessions,
    length,
    periods,
    headline: subject.class_type === 'lab' ? `${plural(sessions, 'lab session')} per week` : `${plural(sessions, 'class', 'classes')} per week`,
    detail: subject.class_type === 'lab'
      ? `Each session needs ${length} consecutive periods (${plural(periods, 'period')} per week in total).`
      : `One period each (${plural(periods, 'period')} per week in total).`,
  };
}

// Compact text for the table, from an API item.
export function needText(item) {
  const { sessions_per_week: n, session_length: length, periods_per_week: total } = item;
  return length > 1 ? `${n} × ${length} periods` + ` (${total}/week)` : `${n} period${n === 1 ? '' : 's'}/week`;
}

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateAssignment(form) {
  const errors = {};
  if (!form.term_id) errors.term_id = 'Choose a term.';
  if (!form.batch_id) errors.batch_id = 'Choose a batch.';
  if (!form.subject_id) errors.subject_id = 'Choose a subject.';
  if (!form.faculty_id) errors.faculty_id = 'Choose a faculty member.';
  return errors;
}

export const toAssignmentPayload = (form) => ({
  term_id: Number(form.term_id),
  batch_id: Number(form.batch_id),
  subject_id: Number(form.subject_id),
  faculty_id: Number(form.faculty_id),
});
