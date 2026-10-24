// Diya - R6 Time-Slot Management: API calls and shared constants.
import { api } from '../../services/api.js';

export const LIST_PATH = '/time-slots';

export const timeSlotsApi = {
  create: (body) => api.post('/time-slots', body),
  update: (id, body) => api.patch(`/time-slots/${id}`, body),
  remove: (id) => api.delete(`/time-slots/${id}`),
};

// Day numbers match the database: 0 = Monday ... 6 = Sunday.
export const DAYS = [
  { value: 0, label: 'Mon', name: 'Monday' },
  { value: 1, label: 'Tue', name: 'Tuesday' },
  { value: 2, label: 'Wed', name: 'Wednesday' },
  { value: 3, label: 'Thu', name: 'Thursday' },
  { value: 4, label: 'Fri', name: 'Friday' },
  { value: 5, label: 'Sat', name: 'Saturday' },
  { value: 6, label: 'Sun', name: 'Sunday' },
];

export const MAX_PERIOD_NO = 20;

// Mirrors the server rules so mistakes are caught before a request is sent. The server still validates everything.
export function validateTimeSlot(form, mode) {
  const errors = {};
  if (mode === 'create' && form.days.length === 0) errors.days = 'Select at least one day.';
  const period = Number(form.period_no);
  if (form.period_no === '' || !Number.isInteger(period) || period < 1 || period > MAX_PERIOD_NO) {
    errors.period_no = `Enter a whole number from 1 to ${MAX_PERIOD_NO}.`;
  }
  if (!form.start_time) errors.start_time = 'Choose a start time.';
  if (!form.end_time) errors.end_time = 'Choose an end time.';
  if (form.start_time && form.end_time && form.start_time >= form.end_time) errors.end_time = 'End time must be after the start time.';
  return errors;
}

export function toPayload(form, mode) {
  const base = {
    period_no: Number(form.period_no),
    start_time: form.start_time,
    end_time: form.end_time,
    slot_type: form.slot_type,
    is_active: form.is_active,
  };
  return mode === 'create' ? { days: form.days, ...base } : { day_of_week: form.day_of_week, ...base };
}
