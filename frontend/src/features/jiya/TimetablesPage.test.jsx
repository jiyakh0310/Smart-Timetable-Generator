import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import TimetablesPage from './TimetablesPage.jsx';
import { batchesIn, buildGrid } from './timetables.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
const timetable = (over = {}) => ({
  id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, generated_at: '2026-10-01T10:00:00',
  periods: 36, unscheduled_sessions: 0, can_discard: true, ...over,
});
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const slot = (day, name, period, start, end, type = 'class', active = true) => ({ id: day * 10 + period, day_of_week: day, day_name: name, period_no: period, start_time: start, end_time: end, slot_type: type, is_active: active });
const SLOTS = [
  slot(0, 'Monday', 1, '09:00', '10:00'), slot(0, 'Monday', 2, '10:00', '11:00'), slot(0, 'Monday', 3, '11:00', '12:00', 'break'),
  slot(1, 'Tuesday', 1, '09:00', '10:00'), slot(1, 'Tuesday', 2, '10:00', '11:00'), slot(1, 'Tuesday', 3, '11:00', '12:00', 'break'), slot(2, 'Wednesday', 1, '09:00', '10:00', 'class', false),
];
const entry = (id, batch, subject, dayNo, periodNo, over = {}) => ({
  id, assignment_id: subject.assignment, batch, subject: { id: 1, code: subject.code, name: subject.name, class_type: subject.type || 'theory' },
  faculty: { id: 1, name: 'Dr. Meera Rao' }, room: { id: 1, code: 'R201' }, time_slot: { id: dayNo * 10 + periodNo, day_of_week: dayNo, period_no: periodNo }, ...over,
});
const A = { id: 1, name: 'CSE Sem 3 - A' };
const B = { id: 2, name: 'CSE Sem 3 - B' };
const DS = { assignment: 1, code: 'CS301', name: 'Data Structures' };
const LAB = { assignment: 2, code: 'CS351', name: 'DS Lab', type: 'lab' };
const detail = (over = {}) => ({
  ...timetable({ periods: 4, unscheduled_sessions: 1 }),
  entries: [entry(1, A, DS, 0, 1), entry(2, A, LAB, 1, 1), entry(3, A, LAB, 1, 2), entry(4, B, DS, 0, 2)],
  unscheduled: [{ id: 1, assignment_id: 3, session_no: 2, batch: B, subject: { id: 3, code: 'CS303', name: 'Operating Systems' }, faculty: { id: 2, name: 'Prof. Anil Rao' }, reason_code: 'faculty_busy', reason_text: 'No free period remains for CS303 for CSE Sem 3 - B.' }],
  ...over,
});

const renderPage = () => render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((url) => {
    if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable(), timetable({ id: 2, version: 2, name: 'Autumn 2026 timetable v2', status: 'approved', can_discard: false, unscheduled_sessions: 3 })]));
    if (url.startsWith('/timetables/')) return Promise.resolve(detail());
    if (url.startsWith('/time-slots')) return Promise.resolve({ items: SLOTS });
    if (url === '/terms') return Promise.resolve({ items: [{ id: 1, name: 'Autumn 2026', academic_year: '2026-27', is_active: true }, { id: 2, name: 'Spring 2026', academic_year: '2025-26', is_active: false }] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
});

describe('Timetables screen - listing', () => {
  it('shows versions with status, scheduled periods and unscheduled counts', async () => {
    renderPage();
    const v1 = await screen.findByRole('row', { name: /timetable v1/ });
    expect(within(v1).getByText('v1')).toBeInTheDocument();
    expect(within(v1).getByText('Draft')).toBeInTheDocument();
    expect(within(v1).getByText('36 periods')).toBeInTheDocument();
    expect(within(v1).getByText('None')).toBeInTheDocument();
    const v2 = screen.getByRole('row', { name: /timetable v2/ });
    expect(within(v2).getByText('Approved')).toBeInTheDocument();
    expect(within(v2).getByText('3 sessions')).toBeInTheDocument();
  });

  it('only drafts can be discarded', async () => {
    renderPage();
    const v1 = await screen.findByRole('row', { name: /timetable v1/ });
    expect(within(v1).getByRole('button', { name: /Discard Autumn 2026 timetable v1/ })).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /timetable v2/ })).queryByRole('button', { name: /Discard/ })).not.toBeInTheDocument();
  });

  it('shows an empty state with a Generate action', async () => {
    api.get.mockImplementation((url) => (url.startsWith('/timetables?') ? Promise.resolve(listOf([])) : Promise.reject(new Error('x'))));
    renderPage();
    expect(await screen.findByText('No timetables yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Generate timetable/ }).length).toBeGreaterThan(1);
  });

  it('shows an error with a retry', async () => {
    api.get.mockRejectedValue(new Error('Server unavailable'));
    renderPage();
    expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('Generate dialog', () => {
  async function open() {
    renderPage();
    await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(screen.getAllByRole('button', { name: /Generate timetable/ })[0]);
    return screen.findByRole('dialog', { name: 'Generate timetable' });
  }

  it('offers only active terms, preselects the only one and says nothing is published', async () => {
    const dialog = await open();
    await waitFor(() => expect(within(dialog).getByLabelText('Term')).toHaveValue('1'));
    expect(within(dialog).queryByRole('option', { name: /Spring 2026/ })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/nothing is approved or published/)).toBeInTheDocument();
  });

  it('generates for the chosen term and shows the real summary with warnings and reasons', async () => {
    api.post.mockResolvedValue({
      ...timetable({ id: 9, name: 'Autumn 2026 timetable v3', version: 3 }),
      generation: { status: 'partial', required_sessions: 32, scheduled_sessions: 30, unscheduled_sessions: 2, scheduled_periods: 34, unscheduled_reasons: { faculty_busy: 1, no_suitable_room: 1 }, warnings: ['1 session had to be placed outside a faculty member\'s preferred periods (a preference, not a rule).'] },
    });
    const dialog = await open();
    await waitFor(() => expect(within(dialog).getByLabelText('Term')).toHaveValue('1'));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Generate draft' }));
    expect(api.post).toHaveBeenCalledWith('/timetables/generate', { term_id: 1 });
    const done = await screen.findByRole('dialog', { name: 'Draft timetable generated' });
    expect(within(done).getByText('Partly scheduled')).toBeInTheDocument();
    expect(within(done).getByText('32')).toBeInTheDocument();
    expect(within(done).getByText('30 (34 periods)')).toBeInTheDocument();
    expect(within(done).getByText(/Faculty already teaching: 1 · No suitable room: 1/)).toBeInTheDocument();
    expect(within(done).getByText(/preference, not a rule/)).toBeInTheDocument();
    expect(within(done).getByText(/saved as a/)).toHaveTextContent('draft');
  });

  it('shows the server refusal and keeps the dialog open', async () => {
    api.post.mockRejectedValue(new Error('This term has no teaching assignments, so there is nothing to schedule.'));
    const dialog = await open();
    await waitFor(() => expect(within(dialog).getByLabelText('Term')).toHaveValue('1'));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Generate draft' }));
    expect(await within(dialog).findByText(/nothing to schedule/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Draft timetable generated' })).not.toBeInTheDocument();
  });

  it('warns when there is no active term and cannot submit', async () => {
    api.get.mockImplementation((url) => {
      if (url === '/terms') return Promise.resolve({ items: [{ id: 2, name: 'Spring 2026', academic_year: '2025-26', is_active: false }] });
      return Promise.resolve(listOf([timetable()]));
    });
    const dialog = await open();
    expect(await within(dialog).findByText(/no active term/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Generate draft' })).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('Timetable detail', () => {
  async function view() {
    renderPage();
    const row = await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(within(row).getByRole('button', { name: /View Autumn 2026 timetable v1/ }));
    return screen.findByRole('heading', { name: 'Autumn 2026 timetable v1' });
  }

  it('shows the batch grid with breaks and a 2-period lab spanning both rows', async () => {
    await view();
    expect(screen.getByLabelText('Batch')).toHaveValue('1');
    const table = screen.getByRole('table', { name: 'Weekly timetable' });
    expect(within(table).getByText(/CS301 · Data Structures/)).toBeInTheDocument();
    const lab = within(table).getByText(/CS351 · DS Lab/);
    expect(lab.closest('td')).toHaveAttribute('rowspan', '2');
    expect(within(table).getAllByText('Break').length).toBeGreaterThan(0);
    expect(within(table).queryByText(/Wed/)).not.toBeInTheDocument(); // a disabled day has no column
  });

  it('switches batch and shows only that batch', async () => {
    await view();
    await userEvent.selectOptions(screen.getByLabelText('Batch'), '2');
    const table = screen.getByRole('table', { name: 'Weekly timetable' });
    expect(within(table).queryByText(/CS351/)).not.toBeInTheDocument();
    expect(within(table).getByText(/CS301/)).toBeInTheDocument();
  });

  it('lists each unscheduled session with its reason', async () => {
    await view();
    const row = screen.getByRole('row', { name: /CS303/ });
    expect(within(row).getByText('Faculty already teaching')).toBeInTheDocument();
    expect(within(row).getByText(/No free period remains for CS303/)).toBeInTheDocument();
    expect(within(row).getByText('Prof. Anil Rao')).toBeInTheDocument();
  });

  it('shows the all-scheduled message when nothing is left over', async () => {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.startsWith('/timetables/')) return Promise.resolve(detail({ unscheduled: [], unscheduled_sessions: 0 }));
      return Promise.resolve({ items: SLOTS });
    });
    await view();
    expect(screen.getByText('Every required session was scheduled')).toBeInTheDocument();
  });

  it('goes back to the list', async () => {
    await view();
    await userEvent.click(screen.getByRole('button', { name: /All versions/ }));
    expect(await screen.findByRole('row', { name: /timetable v2/ })).toBeInTheDocument();
  });

  it('shows a load error with a way back', async () => {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      return Promise.reject(new Error('Timetable not found.'));
    });
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
    expect(await screen.findByText('Timetable not found.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /All versions/ })).toBeInTheDocument();
  });
});

describe('Discard draft', () => {
  it('asks for confirmation, then deletes and reloads', async () => {
    api.delete.mockResolvedValue({});
    renderPage();
    const row = await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(within(row).getByRole('button', { name: /Discard/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Discard this draft?' });
    expect(within(dialog).getByText(/permanently removed/)).toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Discard draft' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/timetables/1'));
    expect(await screen.findByText('Draft discarded')).toBeInTheDocument();
  });

  it('cancelling does nothing', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(within(row).getByRole('button', { name: /Discard/ }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('reports a server refusal', async () => {
    api.delete.mockRejectedValue(new Error('Only a draft can be discarded; this timetable is approved.'));
    renderPage();
    const row = await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(within(row).getByRole('button', { name: /Discard/ }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Discard draft' }));
    expect(await screen.findByText('Could not discard the draft')).toBeInTheDocument();
    expect(screen.getByText(/Only a draft can be discarded/)).toBeInTheDocument();
  });
});

describe('grid helpers', () => {
  it('buildGrid ignores disabled slots and merges only consecutive periods of one lab', () => {
    const d = detail();
    const grid = buildGrid(SLOTS, d.entries, 1);
    expect(grid.days.map((x) => x.label)).toEqual(['Mon', 'Tue']);
    expect(grid.periods.map((p) => p.kind)).toEqual(['class', 'class', 'break']);
    const lab = grid.entries.find((e) => e.kind === 'lab');
    expect(lab).toMatchObject({ dayKey: 1, periodKey: 1, span: 2 });
    expect(grid.entries).toHaveLength(2);
  });

  it('two separate lab sessions on one day are not merged', () => {
    const rows = [entry(1, A, LAB, 1, 1), entry(2, A, LAB, 1, 2), entry(3, A, LAB, 1, 4)];
    const grid = buildGrid(SLOTS, rows, 1);
    expect(grid.entries.map((e) => e.span)).toEqual([2, 1]);
  });

  it('batchesIn lists batches from scheduled and unscheduled work, sorted by name', () => {
    expect(batchesIn(detail()).map((b) => b.name)).toEqual(['CSE Sem 3 - A', 'CSE Sem 3 - B']);
    expect(batchesIn({ entries: [], unscheduled: detail().unscheduled })).toEqual([{ id: 2, name: 'CSE Sem 3 - B' }]);
  });
});
