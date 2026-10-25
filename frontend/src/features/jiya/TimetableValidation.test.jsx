import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import TimetablesPage from './TimetablesPage.jsx';
import { validationState } from './timetables.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
const timetable = (over = {}) => ({
  id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, validated_at: null,
  generated_at: '2026-10-01T10:00:00', periods: 36, unscheduled_sessions: 0, can_discard: true, can_edit: true, ...over,
});
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });
const BATCH = { id: 1, name: 'CSE Sem 3 - A' };
const detail = (over = {}) => ({
  ...timetable(),
  entries: [{
    id: 1, assignment_id: 1, batch: BATCH, subject: { id: 1, code: 'CS301', name: 'Data Structures', class_type: 'theory' }, faculty: { id: 1, name: 'Dr. Meera Rao' },
    room: { id: 1, code: 'R201' }, time_slot: { id: 1, day_of_week: 0, period_no: 1 },
  }],
  unscheduled: [],
  ...over,
});
const SLOTS = [{ id: 1, day_of_week: 0, day_name: 'Monday', period_no: 1, start_time: '09:00', end_time: '10:00', slot_type: 'class', is_active: true }];

const PASSED = {
  timetable_id: 1, status: 'validated', validation_passed: true, is_valid: true, is_complete: true, validated_at: '2026-10-02T09:00:00',
  counts: { required_sessions: 32, scheduled_sessions: 32, unscheduled_sessions: 0, scheduled_periods: 36, hard_errors: 0, warnings: 0 },
  hard_errors: [], warnings: [], unscheduled: [],
};
const FAILED = {
  ...PASSED, status: 'draft', validation_passed: false, is_valid: false, is_complete: false,
  counts: { required_sessions: 32, scheduled_sessions: 30, unscheduled_sessions: 2, scheduled_periods: 34, hard_errors: 2, warnings: 1 },
  hard_errors: [
    { code: 'room_too_small', severity: 'hard', message: 'R101 seats 40 but CSE Sem 3 - A has 58 students.', details: {} },
    { code: 'faculty_unavailable', severity: 'hard', message: 'Dr. Meera Rao is marked unavailable in Monday period 1.', details: {} },
  ],
  warnings: [{ code: 'outside_preferred_slots', severity: 'advisory', message: 'Dr. Meera Rao has preferred time slots and Tuesday period 2 is not one of them.', details: {} }],
  unscheduled: [
    { assignment_id: 3, session_no: 2, batch: BATCH, subject: { id: 3, code: 'CS303', name: 'Operating Systems' }, faculty: { id: 2, name: 'Prof. Anil Rao' }, reason_code: 'rooms_busy', reason_text: 'No free period remains for CS303.' },
    { assignment_id: 4, session_no: null, batch: BATCH, subject: { id: 4, code: 'MA301', name: 'Discrete Mathematics' }, faculty: { id: 3, name: 'Dr. Sunil Das' }, reason_code: 'not_scheduled', reason_text: 'No class is scheduled for MA301 and no reason was recorded.' },
  ],
};

let current;
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  current = detail();
  api.get.mockImplementation((url) => {
    if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
    if (url.startsWith('/timetables/')) return Promise.resolve(current);
    if (url.startsWith('/time-slots')) return Promise.resolve({ items: SLOTS });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
});

async function openDetail() {
  render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
  const row = await screen.findByRole('row', { name: /timetable v1/ });
  await userEvent.click(within(row).getByRole('button', { name: /View/ }));
  return screen.findByRole('heading', { name: 'Autumn 2026 timetable v1' });
}

describe('Validation - before running', () => {
  it('says the timetable has not been validated and offers a keyboard-reachable Validate button', async () => {
    await openDetail();
    expect(screen.getByText(/has not been validated yet/)).toBeInTheDocument();
    const detailBar = screen.getByRole('heading', { name: 'Autumn 2026 timetable v1' }).parentElement;
    expect(within(detailBar).getByText('Not validated')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: /Validate/ });
    await userEvent.tab(); // reachable by keyboard
    button.focus();
    expect(button).toHaveFocus();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('the list shows the recorded validation state', async () => {
    api.get.mockImplementation((url) => (url.startsWith('/timetables?')
      ? Promise.resolve(listOf([timetable(), timetable({ id: 2, name: 'Autumn 2026 timetable v2', validation_passed: true, validated_at: 'x', status: 'validated' }), timetable({ id: 3, name: 'Autumn 2026 timetable v3', validated_at: 'x' })]))
      : Promise.reject(new Error('x'))));
    render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
    expect(within(await screen.findByRole('row', { name: /timetable v1/ })).getByText('Not validated')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /timetable v2/ })).getByText('Validation passed')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /timetable v3/ })).getByText('Validation failed')).toBeInTheDocument();
  });

  it('validationState maps the recorded fields', () => {
    expect(validationState({ validation_passed: true, validated_at: 'x' }).label).toBe('Validation passed');
    expect(validationState({ validation_passed: false, validated_at: 'x' }).label).toBe('Validation failed');
    expect(validationState({ validation_passed: false, validated_at: null }).label).toBe('Not validated');
  });
});

describe('Validation - success', () => {
  it('posts to the validate endpoint and shows a clear pass that does not claim approval', async () => {
    api.post.mockResolvedValue(PASSED);
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    expect(api.post).toHaveBeenCalledWith('/timetables/1/validate', {});
    const card = (await screen.findByText(/Validation passed\./)).closest('section');
    expect(within(card).getByText(/not approved or published/)).toBeInTheDocument();
    expect(within(card).getByText('32')).toBeInTheDocument();
    expect(within(card).getByText('32 (36 periods)')).toBeInTheDocument();
    expect(within(card).getByText(/No hard conflicts/)).toBeInTheDocument();
    expect(within(card).getByText('No warnings.')).toBeInTheDocument();
    expect(within(card).getByText('Every required session is scheduled')).toBeInTheDocument();
    const bar = screen.getByRole('heading', { name: 'Autumn 2026 timetable v1' }).parentElement;
    expect(within(bar).getByText('Validated')).toBeInTheDocument();
    expect(within(bar).getByText('Validation passed')).toBeInTheDocument();
    expect(screen.queryByText(/has not been validated yet/)).not.toBeInTheDocument();
  });

  it('moves focus to the result so keyboard and screen-reader users hear the outcome', async () => {
    api.post.mockResolvedValue(PASSED);
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Validation passed', hidden: true })).toHaveFocus());
  });
});

describe('Validation - failure and warnings', () => {
  it('lists hard errors, warnings, counts and every missing session with its reason', async () => {
    api.post.mockResolvedValue(FAILED);
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    const card = (await screen.findByText(/Validation failed\./)).closest('section');
    expect(within(card).getByText(/2 hard errors must be fixed and 2 required sessions are not scheduled/)).toBeInTheDocument();
    expect(within(card).getByText(/R101 seats 40 but CSE Sem 3 - A has 58 students/)).toBeInTheDocument();
    expect(within(card).getByText(/marked unavailable in Monday period 1/)).toBeInTheDocument();
    expect(within(card).getByText('room too small')).toBeInTheDocument();
    expect(within(card).getByText(/never make validation fail/)).toBeInTheDocument();
    expect(within(card).getByText(/preferred time slots/)).toBeInTheDocument();
    const missing = within(card).getByRole('row', { name: /CS303/ });
    expect(within(missing).getByText('No free room')).toBeInTheDocument();
    expect(within(missing).getByText(/No free period remains/)).toBeInTheDocument();
    expect(within(within(card).getByRole('row', { name: /MA301/ })).getByText('Not scheduled')).toBeInTheDocument();
    const bar = screen.getByRole('heading', { name: 'Autumn 2026 timetable v1' }).parentElement;
    expect(within(bar).getByText('Validation failed')).toBeInTheDocument();
    expect(within(bar).getByText('Draft')).toBeInTheDocument();
  });

  it('a timetable that is only incomplete says so and shows no hard errors', async () => {
    api.post.mockResolvedValue({ ...FAILED, is_valid: true, counts: { ...FAILED.counts, hard_errors: 0, warnings: 0 }, hard_errors: [], warnings: [] });
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    const card = (await screen.findByText(/Validation failed\./)).closest('section');
    expect(within(card).getByText(/2 required sessions are not scheduled/)).toBeInTheDocument();
    expect(within(card).queryByText(/must be fixed/)).not.toBeInTheDocument();
    expect(within(card).getByText(/No hard conflicts/)).toBeInTheDocument();
  });

  it('warnings alone still pass', async () => {
    api.post.mockResolvedValue({ ...PASSED, counts: { ...PASSED.counts, warnings: 1 }, warnings: FAILED.warnings });
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    const card = (await screen.findByText(/Validation passed\./)).closest('section');
    expect(within(card).getByText(/preferred time slots/)).toBeInTheDocument();
  });
});

describe('Validation - loading and errors', () => {
  it('shows a loading state, disables the button while running, then the result', async () => {
    let finish;
    api.post.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    expect(await screen.findByText('Validating the saved timetable…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Validate/ })).toBeDisabled();
    finish(PASSED);
    expect(await screen.findByText(/Validation passed\./)).toBeInTheDocument();
    expect(screen.queryByText('Validating the saved timetable…')).not.toBeInTheDocument();
  });

  it('shows the server error and allows trying again', async () => {
    api.post.mockRejectedValueOnce(new Error('Timetable not found.')).mockResolvedValueOnce(PASSED);
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    expect(await screen.findByText('Timetable not found.')).toBeInTheDocument();
    expect(screen.queryByText(/Validation passed\./)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    expect(await screen.findByText(/Validation passed\./)).toBeInTheDocument();
    expect(screen.queryByText('Timetable not found.')).not.toBeInTheDocument();
  });

  it('a validated timetable can still be discarded from the detail view', async () => {
    api.post.mockResolvedValue(PASSED);
    await openDetail();
    await userEvent.click(screen.getByRole('button', { name: /Validate/ }));
    await screen.findByText(/Validation passed\./);
    expect(screen.getByRole('button', { name: /Discard/ })).toBeInTheDocument();
  });

  it('an approved timetable offers neither Validate nor Discard (the workflow re-validates it itself)', async () => {
    current = detail({ status: 'approved', can_discard: false, can_edit: false, validated_at: 'x', validation_passed: true });
    await openDetail();
    expect(screen.queryByRole('button', { name: /Discard/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Validate/ })).not.toBeInTheDocument();
  });
});
