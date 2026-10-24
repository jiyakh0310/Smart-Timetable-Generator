// Isha - R2 Faculty management: API calls, form rules and the password helper.
import { api } from '../../services/api.js';

export const FACULTY_PATH = '/faculty';
export const facultyApi = {
  create: (body) => api.post('/faculty', body),
  update: (id, body) => api.patch(`/faculty/${id}`, body),
  remove: (id) => api.delete(`/faculty/${id}`),
  resetPassword: (id, password) => api.post(`/faculty/${id}/reset-password`, { password }),
};

export const MAX_WEEKLY_HOURS = 40;
export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 128;
const CODE = /^[A-Z0-9][A-Z0-9._/-]*$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Same rule as the server: 8-128 characters, a letter and a number, not the email / employee code / name.
export function passwordProblem(password, identity = []) {
  if (!password) return 'Enter a password.';
  if (password.length < MIN_PASSWORD || password.length > MAX_PASSWORD) return `Use ${MIN_PASSWORD} to ${MAX_PASSWORD} characters.`;
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return 'Include at least one letter and one number.';
  if (identity.some((v) => v && v.trim().toLowerCase() === password.trim().toLowerCase())) return 'The password must not be the same as the email, employee code or name.';
  return '';
}

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateFaculty(form, mode) {
  const errors = {};
  const name = form.name.trim().replace(/\s+/g, ' ');
  if (!name) errors.name = "Enter the faculty member's name.";
  else if (name.length < 2 || name.length > 120) errors.name = 'Use 2 to 120 characters.';
  const email = form.email.trim();
  if (!email) errors.email = 'Enter the login email address.';
  else if (email.length > 255 || !EMAIL.test(email)) errors.email = 'Enter a valid email address, e.g. name@college.edu.';
  const code = form.employee_code.trim().toUpperCase();
  if (!code) errors.employee_code = 'Enter the employee code, e.g. F001.';
  else if (code.length > 30 || !CODE.test(code)) errors.employee_code = 'Use up to 30 letters, digits or . _ / - (e.g. F001).';
  if (!form.department_id) errors.department_id = 'Choose a department.';
  if (form.designation.trim().length > 80) errors.designation = 'Use up to 80 characters.';
  const hours = Number(form.max_weekly_hours);
  if (form.max_weekly_hours === '' || !Number.isInteger(hours) || hours < 1 || hours > MAX_WEEKLY_HOURS) {
    errors.max_weekly_hours = `Enter a whole number from 1 to ${MAX_WEEKLY_HOURS}.`;
  }
  if (mode === 'create') {
    const problem = passwordProblem(form.password, [email, code, name]);
    if (problem) errors.password = problem;
  }
  return errors;
}

export function toFacultyPayload(form, mode) {
  const payload = {
    name: form.name.trim(),
    email: form.email.trim(),
    employee_code: form.employee_code.trim(),
    department_id: Number(form.department_id),
    designation: form.designation.trim() || null,
    max_weekly_hours: Number(form.max_weekly_hours),
  };
  if (mode === 'create') payload.password = form.password;
  else payload.is_active = form.is_active;
  return payload;
}

// A random password from the browser's secure generator (no look-alike characters such as 0/O or 1/l).
const LETTERS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
const DIGITS = '23456789';
const SYMBOLS = '@#%+=';
export function generatePassword(length = 14, rng = globalThis.crypto) {
  const alphabet = LETTERS + DIGITS + SYMBOLS;
  const pick = (chars) => {
    const limit = 256 - (256 % chars.length); // reject values that would bias the choice
    const byte = new Uint8Array(1);
    do { rng.getRandomValues(byte); } while (byte[0] >= limit);
    return chars[byte[0] % chars.length];
  };
  for (;;) {
    const candidate = Array.from({ length }, () => pick(alphabet)).join('');
    if (/[A-Za-z]/.test(candidate) && /\d/.test(candidate)) return candidate;
  }
}
