import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider, WeeklyTimetable } from '../../components/ui';
import TimetablesPage from './TimetablesPage.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
const BATCH = { id: 1, name: 'CSE Sem 3 - A' };
const slot = (id, day, name, period, start, end, type = 'class') => ({ id, day_of_week: day, day_name: name, period_no: period, start_time: start, end_time: end, slot_type: type, is_active: true });
const SLOTS = [slot(1, 0, 'Monday', 1, '09:00', '10:00'), slot(2, 0, 'Monday', 2, '10:00', '11:00'), slot(3, 1, 'Tuesday', 1, '09:00', '10:00'), slot(4, 1, 'Tuesday', 2, '10:00', '11:00')];
const entry = (id, subject, slotNo, dayNo, periodNo, type = 'theory') => ({
  id, assignment_id: id, batch: BATCH, subject: { id, code: subject, name: `${subject} name`, class_type: type }, faculty: { id: 1, name: 'Dr. Meera Rao' },
  room: { id: 1, code: 'R201' }, time_slot: { id: slotNo, day_of_week: dayNo, period_no: periodNo },
});
const timetable = (over = {}) => ({
  id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, validated_at: null, generated_at: '2026-10-01T10:00:00',
  periods: 3, unscheduled_sessions: 0, can_discard: true, can_edit: true, ...over,
});
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });
const detail = (over = {}) => ({ ...timetable(), entries: [entry(1, 'CS301', 1, 0, 1), entry(2, 'CS351', 2, 0, 2, 'lab')], unscheduled: [], workload: [], ...over });

const room = (id, code, cap, current = false) => ({ id, code, name: `Room ${code}`, capacity: cap, room_type: 'classroom', is_current: current });
const OPTIONS = {
  entry_id: 1, entry_ids: [1], periods: 1, subject: { code: 'CS301', name: 'Data Structures', class_type: 'theory' }, batch: BATCH, faculty: { id: 1, name: 'Dr. Meera Rao' },
  current: { time_slot_id: 1, room_id: 1 },
  options: [
    { time_slot_id: 1, day_of_week: 0, day_name: 'Monday', period_no: 1, start_time: '09:00', end_time: '10:00', is_current: true, rooms: [room(1, 'R201', 60, true), room(2, 'R202', 70)] },
    { time_slot_id: 3, day_of_week: 1, day_name: 'Tuesday', period_no: 1, start_time: '09:00', end_time: '10:00', is_current: false, rooms: [room(2, 'R202', 70)] },
  ],
};
const PASSED = {
  timetable_id: 1, status: 'validated', validation_passed: true, is_valid: true, is_complete: true, validated_at: '2026-10-02T09:00:00',
  counts: { required_sessions: 2, scheduled_sessions: 2, unscheduled_sessions: 0, scheduled_periods: 3, hard_errors: 0, warnings: 0 }, hard_errors: [], warnings: [], unscheduled: [],
};

let current;
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  current = detail();
  api.get.mockImplementation((url) => {
    if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
    if (url.includes('/edit-options')) return Promise.resolve(OPTIONS);
    if (url.startsWith('/timetables/')) return Promise.resolve(current);
    if (url.startsWith('/time-slots')) return Promise.resolve({ items: SLOTS });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
});

async function openDetail() {
  render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
  await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
  return screen.findByRole('heading', { name: 'Autumn 2026 timetable v1' });
}

const grid = () => screen.getByRole('table', { name: 'Weekly timetable' });

describe('WeeklyTimetable - clickable entries', () => {
  const days = [{ key: 0, label: 'Mon', name: 'Monday' }];
  const periods = [{ key: 1, start: '09:00', end: '10:00', kind: 'class' }];
  const entries = [{ id: 7, dayKey: 0, periodKey: 1, title: 'CS301', kind: 'theory' }];

  it('is read-only without a handler', () => {
    render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    expect(screen.queryByRole('button', { name: /Move CS301/ })).not.toBeInTheDocument();
  });

  it('renders each class as a labelled button that reports the entry', async () => {
    const onEntryClick = vi.fn();
    render(<WeeklyTimetable days={days} periods={periods} entries={entries} onEntryClick={onEntryClick} />);
    await userEvent.click(screen.getAllByRole('button', { name: 'Move CS301, Monday 09:00' })[0]);
    expect(onEntryClick).toHaveBeenCalledWith(entries[0]);
  });
});

describe('Editing a class', () => {
  it('opens from the grid with the keyboard and lists the eligible times and rooms', async () => {
    await openDetail();
    const button = within(grid()).getByRole('button', { name: 'Move CS301 · CS301 name, Monday 09:00' });
    button.focus();
    await userEvent.keyboard('{Enter}');
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    expect(api.get).toHaveBeenCalledWith('/timetables/1/entries/1/edit-options');
    expect(within(dialog).getByLabelText('Day and time')).toHaveValue('1');
    expect(within(dialog).getByRole('option', { name: /Monday · period 1 · 09:00–10:00 \(current\)/ })).toBeInTheDocument();
    expect(within(dialog).getByRole('option', { name: /Tuesday · period 1/ })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Room')).toHaveValue('1');
    expect(within(dialog).getByRole('option', { name: /R201 · Room R201 · 60 seats \(current\)/ })).toBeInTheDocument();
    expect(within(dialog).getByText(/re-validated/)).toBeInTheDocument();
  });

  it('cannot save until something changes, and the rooms follow the chosen time', async () => {
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    const save = within(dialog).getByRole('button', { name: 'Save change' });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(within(dialog).getByLabelText('Day and time'), '3');
    expect(within(dialog).getAllByRole('option', { name: /seats/ })).toHaveLength(1);
    expect(within(dialog).getByLabelText('Room')).toHaveValue('2');
    expect(save).toBeEnabled();
  });

  it('saves, closes, shows the fresh validation result and the new grid', async () => {
    const moved = detail({ entries: [entry(9, 'CS301', 3, 1, 1), entry(2, 'CS351', 2, 0, 2, 'lab')], status: 'validated', validation_passed: true });
    api.patch.mockResolvedValue({ timetable: moved, edited_entry_ids: [9], warnings: [], validation: PASSED });
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    await userEvent.selectOptions(within(dialog).getByLabelText('Day and time'), '3');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save change' }));
    expect(api.patch).toHaveBeenCalledWith('/timetables/1/entries/1', { time_slot_id: 3, room_id: 2 });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Move class' })).not.toBeInTheDocument());
    expect(await screen.findByText('Class moved')).toBeInTheDocument();
    expect(screen.getByText(/Validation passed\./)).toBeInTheDocument();
    expect(within(grid()).getByRole('button', { name: /Move CS301 · CS301 name, Tuesday 09:00/ })).toBeInTheDocument();
    expect(within(screen.getByRole('heading', { name: 'Autumn 2026 timetable v1' }).parentElement).getByText('Validated')).toBeInTheDocument();
  });

  it('keeps the dialog open and explains a refused change', async () => {
    const err = Object.assign(new Error('Dr. Meera Rao is already teaching in Tuesday period 1, which overlaps Tuesday period 1. (+1 more problem)'), {
      details: { conflicts: [{ code: 'faculty_clash', message: 'Dr. Meera Rao is already teaching in Tuesday period 1.' }, { code: 'room_clash', message: 'R202 is already booked on Tuesday period 1.' }] },
    });
    api.patch.mockRejectedValue(err);
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    await userEvent.selectOptions(within(dialog).getByLabelText('Day and time'), '3');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save change' }));
    expect(await within(dialog).findByText(/This change was not saved\./)).toBeInTheDocument();
    expect(within(dialog).getByText('R202 is already booked on Tuesday period 1.')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Move class' })).toBeInTheDocument();
    expect(within(grid()).getByRole('button', { name: /Move CS301 · CS301 name, Monday 09:00/ })).toBeInTheDocument(); // grid unchanged
  });

  it('a single refusal shows just its message', async () => {
    api.patch.mockRejectedValue(Object.assign(new Error('A approved timetable cannot be edited.'), { details: {} }));
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    await userEvent.selectOptions(within(dialog).getByLabelText('Day and time'), '3');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save change' }));
    expect(await within(dialog).findByText(/cannot be edited/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('list')).not.toBeInTheDocument();
  });

  it('cancel closes without saving', async () => {
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    await userEvent.click(within(await screen.findByRole('dialog', { name: 'Move class' })).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: 'Move class' })).not.toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('says so when no other position is free', async () => {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.includes('/edit-options')) return Promise.resolve({ ...OPTIONS, options: [OPTIONS.options[0]] });
      if (url.startsWith('/timetables/')) return Promise.resolve(current);
      return Promise.resolve({ items: SLOTS });
    });
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    expect(await screen.findByText(/No other time or room is currently free/)).toBeInTheDocument();
  });

  it('shows a load error with a way out', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/edit-options')) return Promise.reject(new Error('A published timetable cannot be edited.'));
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.startsWith('/timetables/')) return Promise.resolve(current);
      return Promise.resolve({ items: SLOTS });
    });
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS301/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Move class' });
    expect(await within(dialog).findByText(/cannot be edited/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('explains that a lab moves as one block', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/edit-options')) return Promise.resolve({ ...OPTIONS, periods: 2, entry_ids: [2, 3], subject: { code: 'CS351', name: 'DS Lab', class_type: 'lab' } });
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.startsWith('/timetables/')) return Promise.resolve(current);
      return Promise.resolve({ items: SLOTS });
    });
    await openDetail();
    await userEvent.click(within(grid()).getByRole('button', { name: /Move CS351/ }));
    expect(await screen.findByText(/2-period lab; it moves as one block/)).toBeInTheDocument();
  });
});

describe('Immutable timetables', () => {
  it.each(['approved', 'published'])('a %s timetable has no edit buttons and says why', async (status) => {
    current = detail({ status, can_edit: false, can_discard: false });
    await openDetail();
    expect(screen.getByText(new RegExp(`is ${status} and can no longer be edited`))).toBeInTheDocument();
    expect(within(grid()).queryByRole('button', { name: /Move/ })).not.toBeInTheDocument();
    expect(within(grid()).getByText(/CS301 · CS301 name/)).toBeInTheDocument();
  });
});
