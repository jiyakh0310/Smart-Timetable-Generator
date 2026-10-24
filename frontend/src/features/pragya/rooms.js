// Pragya - R5 Classroom and laboratory management: API calls and form rules.
import { api } from '../../services/api.js';

export const ROOMS_PATH = '/rooms';
export const roomsApi = {
  create: (body) => api.post('/rooms', body),
  update: (id, body) => api.patch(`/rooms/${id}`, body),
  remove: (id) => api.delete(`/rooms/${id}`),
};

export const MAX_CAPACITY = 2000;
export const TYPE_LABEL = { classroom: 'Classroom', lab: 'Laboratory', seminar_hall: 'Seminar hall', auditorium: 'Auditorium' };
const CODE = /^[A-Z0-9][A-Z0-9._/-]*$/;

// Mirrors the server rules so mistakes are caught before a request is sent. `minCapacity` is the largest batch already
// scheduled in this room (0 for a new or unscheduled room). The server still validates everything.
export function validateRoom(form, { minCapacity = 0 } = {}) {
  const errors = {};
  const code = form.code.trim().toUpperCase();
  if (!code) errors.code = 'Enter the room code, e.g. R101.';
  else if (code.length > 30 || !CODE.test(code)) errors.code = 'Use up to 30 letters, digits or . _ / - (e.g. R101).';
  const name = form.name.trim().replace(/\s+/g, ' ');
  if (!name) errors.name = 'Enter the room name.';
  else if (name.length < 2 || name.length > 100) errors.name = 'Use 2 to 100 characters.';
  if (form.location.trim().length > 120) errors.location = 'Use up to 120 characters.';
  if (!form.room_type) errors.room_type = 'Choose a room type.';
  const capacity = Number(form.capacity);
  if (form.capacity === '' || !Number.isInteger(capacity) || capacity < 1 || capacity > MAX_CAPACITY) errors.capacity = `Enter a whole number from 1 to ${MAX_CAPACITY}.`;
  else if (capacity < minCapacity) errors.capacity = `A batch of ${minCapacity} students is scheduled here, so the capacity cannot be less than ${minCapacity}.`;
  if (form.lab_type.trim().length > 60) errors.lab_type = 'Use up to 60 characters.';
  return errors;
}

export function toRoomPayload(form) {
  return {
    code: form.code.trim(),
    name: form.name.trim(),
    location: form.location.trim() || null,
    capacity: Number(form.capacity),
    room_type: form.room_type,
    // Only laboratories have a lab type; sending one for another type would be rejected.
    lab_type: form.room_type === 'lab' ? form.lab_type.trim() || null : null,
    is_available: form.is_available,
  };
}
