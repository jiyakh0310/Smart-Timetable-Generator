// Diya - R3 Student management: API calls and form rules.
import { api } from '../../services/api.js';

export const STUDENTS_PATH = '/students';
export const studentsApi = {
  create: (body) => api.post('/students', body),
  update: (id, body) => api.patch(`/students/${id}`, body),
  remove: (id) => api.delete(`/students/${id}`),
};

const ENROLLMENT = /^[A-Z0-9][A-Z0-9._/-]*$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateStudent(form) {
  const errors = {};
  const number = form.enrollment_no.trim().toUpperCase();
  if (!number) errors.enrollment_no = 'Enter the enrollment number, e.g. CSE23001.';
  else if (number.length > 30 || !ENROLLMENT.test(number)) errors.enrollment_no = 'Use up to 30 letters, digits or . _ / - (e.g. CSE23001).';
  const name = form.name.trim().replace(/\s+/g, ' ');
  if (!name) errors.name = "Enter the student's name.";
  else if (name.length < 2 || name.length > 120) errors.name = 'Use 2 to 120 characters.';
  const email = form.email.trim();
  if (email && (email.length > 255 || !EMAIL.test(email))) errors.email = 'Enter a valid email address, e.g. name@college.edu.';
  if (!form.batch_id) errors.batch_id = 'Choose a batch.';
  return errors;
}

export const toStudentPayload = (form) => ({
  enrollment_no: form.enrollment_no.trim(),
  name: form.name.trim(),
  email: form.email.trim() || null,
  batch_id: Number(form.batch_id),
});
