// Diya - R3 Batch management: API calls and form rules.
import { api } from '../../services/api.js';

export const BATCHES_PATH = '/batches';
export const batchesApi = {
  create: (body) => api.post('/batches', body),
  update: (id, body) => api.patch(`/batches/${id}`, body),
  remove: (id) => api.delete(`/batches/${id}`),
};

export const MAX_STRENGTH = 500;
export const MAX_SEMESTER = 12;
const SECTION = /^[A-Za-z0-9]{1,10}$/;
const whole = (v, lo, hi) => v !== '' && Number.isInteger(Number(v)) && Number(v) >= lo && Number(v) <= hi;

// Mirrors the server rules. `program` (selected program row) bounds the semester; `minStrength` is the
// number of students already in the batch when editing. The server still validates everything.
export function validateBatch(form, { program, minStrength = 0 } = {}) {
  const errors = {};
  if (!form.program_id) errors.program_id = 'Choose a program.';
  const maxSem = program?.duration_semesters ?? MAX_SEMESTER;
  if (!whole(form.semester_no, 1, maxSem)) {
    errors.semester_no = program ? `${program.name} has ${maxSem} semesters. Enter a number from 1 to ${maxSem}.` : `Enter a whole number from 1 to ${MAX_SEMESTER}.`;
  }
  if (!SECTION.test(form.section.trim())) errors.section = 'Use 1 to 10 letters or digits, e.g. A.';
  if (!whole(form.strength, 1, MAX_STRENGTH)) errors.strength = `Enter a whole number from 1 to ${MAX_STRENGTH}.`;
  else if (Number(form.strength) < minStrength) errors.strength = `Cannot be less than the ${minStrength} student${minStrength === 1 ? '' : 's'} already in this batch.`;
  const name = form.name.trim();
  if (name && (name.length < 2 || name.length > 80)) errors.name = 'Use 2 to 80 characters, or leave blank to generate one.';
  return errors;
}

export const toBatchPayload = (form) => ({
  program_id: Number(form.program_id),
  semester_no: Number(form.semester_no),
  section: form.section.trim(),
  strength: Number(form.strength),
  name: form.name.trim(),
});

export function usageSentence(usage) {
  const parts = [
    [usage.students, 'student', 'students'],
    [usage.teaching_assignments, 'teaching assignment', 'teaching assignments'],
    [usage.timetable_entries, 'timetable entry', 'timetable entries'],
    [usage.announcements, 'announcement', 'announcements'],
  ].filter(([n]) => n > 0).map(([n, one, many]) => `${n} ${n === 1 ? one : many}`);
  return parts.join(', ');
}
