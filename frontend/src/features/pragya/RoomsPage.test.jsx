import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import RoomsPage from './RoomsPage.jsx';
import { toRoomPayload, validateRoom } from './rooms.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const room = (over = {}) => ({
  id: 1, code: 'R101', name: 'Room 101', location: 'Main Block, Floor 1', capacity: 40, room_type: 'classroom', lab_type: null, is_available: true,
  usage: { timetable_entries: 0 }, min_capacity: 0, in_use: false, ...over,
});
const LAB = room({ id: 2, code: 'LAB1', name: 'Computer Lab 1', location: 'IT Block', capacity: 60, room_type: 'lab', lab_type: 'Computer' });
const BUSY = room({ id: 3, code: 'R201', name: 'Room 201', capacity: 60, usage: { timetable_entries: 3 }, min_capacity: 58, in_use: true });
const OFF = room({ id: 4, code: 'R202', name: 'Room 202', capacity: 70, is_available: false });
const ROOMS = [room(), LAB, BUSY, OFF];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><RoomsPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/rooms')).at(-1);
const loaded = () => screen.findByRole('row', { name: /R202/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockResolvedValue(listOf(ROOMS));
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getByRole('button', { name: /Add room/ }));
  return screen.getByRole('dialog', { name: 'Add room or laboratory' });
}

describe('Rooms screen - listing', () => {
  it('shows code, name, location, type, seats, service status and timetable usage', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /R101/ });
    expect(within(row).getByText('Room 101')).toBeInTheDocument();
    expect(within(row).getByText('Main Block, Floor 1')).toBeInTheDocument();
    expect(within(row).getByText('Classroom')).toBeInTheDocument();
    expect(within(row).getByText('40')).toBeInTheDocument();
    expect(within(row).getByText('In service')).toBeInTheDocument();
    expect(within(row).getByText('Not used')).toBeInTheDocument();
    const lab = screen.getByRole('row', { name: /LAB1/ });
    expect(within(lab).getByText('Laboratory')).toBeInTheDocument();
    expect(within(lab).getByText('Computer')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /R201/ })).getByText('3 entries')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /R202/ })).getByText('Out of service')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Rooms & labs' })).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-4 of 4 rooms');
  });

  it('sends type, size and status filters and the search text', async () => {
    renderPage();
    await loaded();
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'Laboratory');
    await waitFor(() => expect(lastList()).toContain('room_type=lab'));
    await userEvent.selectOptions(screen.getByLabelText('Size'), '50+ seats');
    await waitFor(() => expect(lastList()).toContain('min_capacity=50'));
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Out of service');
    await waitFor(() => expect(lastList()).toContain('available=false'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search rooms/ }), 'lab');
    await waitFor(() => expect(lastList()).toContain('q=lab'));
  });

  it('shows empty and error states', async () => {
    api.get.mockResolvedValue(listOf([]));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No rooms yet' })).toBeInTheDocument();
    unmount();
    api.get.mockRejectedValue(new Error('Cannot reach the server.'));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('Rooms screen - add (PRA-TC01, TC02, TC05, TC06)', () => {
  it('opens with focus on the first field, offers all four types and shows lab type only for laboratories', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByLabelText('Room code')).toHaveFocus();
    expect(within(within(dialog).getByLabelText('Type')).getAllByRole('option').map((o) => o.textContent)).toEqual(['Classroom', 'Laboratory', 'Seminar hall', 'Auditorium']);
    expect(within(dialog).queryByLabelText(/Lab type/)).not.toBeInTheDocument();
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Laboratory');
    expect(within(dialog).getByLabelText(/Lab type/)).toBeInTheDocument();
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Classroom');
    expect(within(dialog).queryByLabelText(/Lab type/)).not.toBeInTheDocument();
  });

  it('PRA-TC05: reports missing code, name and capacity and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add room' }));
    expect(await within(dialog).findByText('Enter the room code, e.g. R101.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter the room name.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 1 to 2000.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it.each([['0'], ['-5'], ['2001'], ['40.5']])('PRA-TC06: rejects the capacity %s before sending', async (capacity) => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Room code'), 'R301');
    await userEvent.type(within(dialog).getByLabelText('Room name'), 'Room 301');
    await userEvent.type(within(dialog).getByLabelText('Seating capacity'), capacity);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add room' }));
    expect(await within(dialog).findByText('Enter a whole number from 1 to 2000.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('PRA-TC01: sends a classroom (no lab type), then toasts, closes and reloads', async () => {
    api.post.mockResolvedValue(room({ id: 9, code: 'R301' }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Room code'), 'r301');
    await userEvent.type(within(dialog).getByLabelText('Room name'), 'Room 301');
    await userEvent.type(within(dialog).getByLabelText('Seating capacity'), '50');
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add room' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/rooms', { code: 'r301', name: 'Room 301', location: null, capacity: 50, room_type: 'classroom', lab_type: null, is_available: true }));
    expect(await screen.findByText('Room added')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('PRA-TC02: sends a laboratory with its lab type', async () => {
    api.post.mockResolvedValue(LAB);
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Room code'), 'LAB3');
    await userEvent.type(within(dialog).getByLabelText('Room name'), 'Electronics Lab');
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Laboratory');
    await userEvent.type(within(dialog).getByLabelText(/Lab type/), 'Electronics');
    await userEvent.type(within(dialog).getByLabelText('Seating capacity'), '40');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add room' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/rooms', expect.objectContaining({ room_type: 'lab', lab_type: 'Electronics', capacity: 40 })));
  });

  it('shows a duplicate room code error from the server on the field and keeps the entered data', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('A room with code R101 already exists.'), { details: { code: 'This room code is already used.' } }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Room code'), 'R101');
    await userEvent.type(within(dialog).getByLabelText('Room name'), 'Another');
    await userEvent.type(within(dialog).getByLabelText('Seating capacity'), '30');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add room' }));
    expect(await within(dialog).findByText('This room code is already used.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Room name')).toHaveValue('Another');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Rooms screen - edit (PRA-TC03)', () => {
  it('prefills a free room and saves a new capacity and type', async () => {
    api.patch.mockResolvedValue(room());
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit R101 Room 101' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit R101' });
    expect(within(dialog).getByLabelText('Seating capacity')).toHaveValue(40);
    expect(within(dialog).getByLabelText('Type')).toBeEnabled();
    const capacity = within(dialog).getByLabelText('Seating capacity');
    await userEvent.clear(capacity);
    await userEvent.type(capacity, '55');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/rooms/1', expect.objectContaining({ capacity: 55, room_type: 'classroom', code: 'R101' })));
    expect(await screen.findByText('Room updated')).toBeInTheDocument();
  });

  it('locks the type of a scheduled room and will not accept a capacity below the largest scheduled batch', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit R201 Room 201' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/used by 3 timetable entries/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot go below 58/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Type')).toBeDisabled();
    const capacity = within(dialog).getByLabelText('Seating capacity');
    await userEvent.clear(capacity);
    await userEvent.type(capacity, '57');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    expect(await within(dialog).findByText(/A batch of 58 students is scheduled here/)).toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
    await userEvent.clear(capacity);
    await userEvent.type(capacity, '58'); // equal is allowed
    api.patch.mockResolvedValue(BUSY);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/rooms/3', expect.objectContaining({ capacity: 58 })));
  });

  it('warns before taking a scheduled room out of service, but allows it', async () => {
    api.patch.mockResolvedValue(room({ ...BUSY, is_available: false }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit R201 Room 201' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).queryByText(/Taking it out of service is allowed/)).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'In service' }));
    expect(within(dialog).getByText(/Taking it out of service is allowed, but validation will report those entries/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/rooms/3', expect.objectContaining({ is_available: false })));
  });

  it('shows the server message when it refuses a change', async () => {
    api.patch.mockRejectedValue(Object.assign(new Error('A batch of 58 students is scheduled in this room, so its capacity cannot be less than 58.'), { details: { capacity: 'Cannot be less than 58 while it is scheduled.' } }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit R101 Room 101' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save changes' }));
    expect(await within(screen.getByRole('dialog')).findByText('Cannot be less than 58 while it is scheduled.')).toBeInTheDocument();
  });
});

describe('Rooms screen - delete', () => {
  it('asks first; Cancel changes nothing; confirming deletes an unused room', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete R101 Room 101' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Delete this room?' })).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Delete R101 Room 101' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/rooms/1'));
    expect(await screen.findByText('Room deleted')).toBeInTheDocument();
  });

  it('explains that a scheduled room cannot be deleted and suggests taking it out of service, with no API call', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete R201 Room 201' }));
    const dialog = screen.getByRole('dialog', { name: 'This room is in use' });
    expect(dialog).toHaveTextContent('used by 3 timetable entries');
    expect(dialog).toHaveTextContent('Mark it out of service instead');
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('shows the server message in an error toast if the delete is refused', async () => {
    api.delete.mockRejectedValue(new Error('This room is used by 1 timetable entry and cannot be deleted.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete R101 Room 101' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete the room')).toBeInTheDocument();
    expect(screen.getByText(/cannot be deleted/)).toBeInTheDocument();
  });
});

describe('room form rules (unit)', () => {
  const ok = { code: 'R101', name: 'Room 101', location: '', capacity: '40', room_type: 'classroom', lab_type: '', is_available: true };

  it('accepts a valid room and builds a payload that only sends a lab type for laboratories', () => {
    expect(validateRoom(ok)).toEqual({});
    expect(toRoomPayload({ ...ok, room_type: 'classroom', lab_type: 'Computer' }).lab_type).toBeNull();
    expect(toRoomPayload({ ...ok, room_type: 'lab', lab_type: ' Computer ' })).toMatchObject({ lab_type: 'Computer', room_type: 'lab', location: null, capacity: 40 });
  });

  it.each([
    [{ code: '' }, 'code'], [{ code: 'bad code' }, 'code'], [{ name: 'x' }, 'name'], [{ capacity: '' }, 'capacity'], [{ capacity: '0' }, 'capacity'],
    [{ capacity: '2001' }, 'capacity'], [{ capacity: '1.5' }, 'capacity'], [{ room_type: '' }, 'room_type'], [{ location: 'l'.repeat(121) }, 'location'],
  ])('flags %j', (over, field) => expect(validateRoom({ ...ok, ...over })).toHaveProperty(field));

  it('accepts the capacity boundaries and enforces the scheduled minimum (equal is fine)', () => {
    expect(validateRoom({ ...ok, capacity: '1' })).toEqual({});
    expect(validateRoom({ ...ok, capacity: '2000' })).toEqual({});
    expect(validateRoom({ ...ok, capacity: '57' }, { minCapacity: 58 })).toHaveProperty('capacity');
    expect(validateRoom({ ...ok, capacity: '58' }, { minCapacity: 58 })).toEqual({});
  });
});
