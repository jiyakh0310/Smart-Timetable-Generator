// Diya - R4 Subject/Course Management: API calls, constants and form rules.
import { api } from '../../services/api.js';

export const SUBJECTS_PATH = '/subjects';

export const subjectsApi = {
  create: (body) => api.post('/subjects', body),
  update: (id, body) => api.patch(`/subjects/${id}`, body),
  remove: (id) => api.delete(`/subjects/${id}`),
};

export const MAX = { semester: 12, credits: 20, weeklyHours: 40, labBlock: 6 };
export const CODE_PATTERN = /^[A-Z0-9][A-Z0-9._/-]*$/;

export const ROOM_LABEL = { classroom: 'Classroom', lab: 'Laboratory', seminar_hall: 'Seminar hall', auditorium: 'Auditorium' };
// Same rule as the server: labs need a laboratory; theory can use any non-lab room.
export const ROOM_OPTIONS = {
  theory: ['classroom', 'seminar_hall', 'auditorium'],
  lab: ['lab'],
};
export const defaultRoom = (classType) => ROOM_OPTIONS[classType][0];

// Fields that decide how many sessions a subject needs; the server locks them once a subject is assigned.
export const LOCKED_FIELDS = ['department_id', 'semester_no', 'class_type', 'weekly_hours', 'lab_block_periods'];

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateSubject(form) {
  const errors = {};
  const code = form.code.trim().toUpperCase();
  if (!code) errors.code = 'Enter the subject code, e.g. CS301.';
  else if (code.length > 20 || !CODE_PATTERN.test(code)) errors.code = 'Use up to 20 letters, digits or . _ / - (e.g. CS301).';

  const name = form.name.trim().replace(/\s+/g, ' ');
  if (!name) errors.name = 'Enter the subject name.';
  else if (name.length < 2 || name.length > 150) errors.name = 'Use 2 to 150 characters.';

  if (!form.department_id) errors.department_id = 'Choose a department.';

  const whole = (value, lo, hi) => value !== '' && Number.isInteger(Number(value)) && Number(value) >= lo && Number(value) <= hi;
  if (!whole(form.semester_no, 1, MAX.semester)) errors.semester_no = `Enter a whole number from 1 to ${MAX.semester}.`;
  if (!whole(form.credits, 0, MAX.credits)) errors.credits = `Enter a whole number from 0 to ${MAX.credits}.`;
  if (!whole(form.weekly_hours, 1, MAX.weeklyHours)) errors.weekly_hours = `Enter a whole number from 1 to ${MAX.weeklyHours}.`;

  if (form.class_type === 'lab') {
    if (!whole(form.lab_block_periods, 1, MAX.labBlock)) errors.lab_block_periods = `Enter a whole number from 1 to ${MAX.labBlock}.`;
    else if (!errors.weekly_hours && Number(form.weekly_hours) % Number(form.lab_block_periods) !== 0) {
      errors.weekly_hours = `Lab hours must be a multiple of the session length (${form.lab_block_periods}).`;
    }
  }
  return errors;
}

export function toPayload(form) {
  const payload = {
    code: form.code.trim(),
    name: form.name.trim(),
    department_id: Number(form.department_id),
    semester_no: Number(form.semester_no),
    credits: Number(form.credits),
    weekly_hours: Number(form.weekly_hours),
    class_type: form.class_type,
    required_room_type: form.required_room_type || null,
  };
  if (form.class_type === 'lab') payload.lab_block_periods = Number(form.lab_block_periods);
  return payload;
}

export function sessionsText(subject) {
  if (subject.class_type === 'lab') {
    const n = subject.sessions_per_week;
    return `${n} session${n === 1 ? '' : 's'} × ${subject.lab_block_periods} periods`;
  }
  return `${subject.sessions_per_week} period${subject.sessions_per_week === 1 ? '' : 's'}`;
}
