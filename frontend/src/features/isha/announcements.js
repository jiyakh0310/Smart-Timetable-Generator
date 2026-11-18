// Isha - R19 Announcements: API calls, categories and form rules.
import { api } from '../../services/api.js';

export const ANNOUNCEMENTS_PATH = '/announcements';           // Admin: every status
export const FEED_PATH = '/announcements/published';          // everyone signed in: published only

export const announcementsApi = {
  create: (body) => api.post('/announcements', body),
  update: (id, body) => api.patch(`/announcements/${id}`, body),
  publish: (id) => api.post(`/announcements/${id}/publish`, {}),
  unpublish: (id) => api.post(`/announcements/${id}/unpublish`, {}),
  remove: (id) => api.delete(`/announcements/${id}`),
};

// tone is the Badge tone; the label is always shown, so category never relies on colour alone.
export const CATEGORIES = [
  { value: 'general', label: 'General', tone: 'neutral' },
  { value: 'academic', label: 'Academic', tone: 'primary' },
  { value: 'timetable_change', label: 'Timetable change', tone: 'info' },
  { value: 'exam', label: 'Exam', tone: 'warning' },
  { value: 'urgent', label: 'Urgent', tone: 'danger' },
];
export const CATEGORY = Object.fromEntries(CATEGORIES.map((c) => [c.value, c]));
export const CATEGORY_OPTIONS = [{ value: '', label: 'All categories' }, ...CATEGORIES.map((c) => ({ value: c.value, label: c.label }))];
export const STATUS_OPTIONS = [{ value: '', label: 'Any status' }, { value: 'published', label: 'Published' }, { value: 'draft', label: 'Draft' }];

export const LIMITS = { titleMin: 3, titleMax: 200, messageMin: 5, messageMax: 5000 };

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateAnnouncement(form) {
  const errors = {};
  const title = form.title.trim().replace(/\s+/g, ' ');
  if (!title) errors.title = 'Enter a title.';
  else if (title.length < LIMITS.titleMin || title.length > LIMITS.titleMax) errors.title = `Use ${LIMITS.titleMin} to ${LIMITS.titleMax} characters.`;
  const message = form.message.trim();
  if (!message) errors.message = 'Write the announcement.';
  else if (message.length < LIMITS.messageMin || message.length > LIMITS.messageMax) errors.message = `Use ${LIMITS.messageMin} to ${LIMITS.messageMax} characters.`;
  if (!CATEGORY[form.category]) errors.category = 'Choose a category.';
  return errors;
}

export const toPayload = (form) => ({ title: form.title.trim(), message: form.message.trim(), category: form.category });

export function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function excerpt(text, max = 220) {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length <= max ? flat : `${flat.slice(0, max).replace(/\s+\S*$/, '')}…`;
}
