import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import TimetablesPage from './TimetablesPage.jsx';
import WorkloadTable from './WorkloadTable.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const row = (over = {}) => ({
  faculty_id: 1, employee_code: 'F001', name: 'Dr. Meera Rao', max_hours: 18, assigned_hours: 10, scheduled_hours: 10, overload_hours: 0, over_assigned_hours: 0, status: 'ok', ...over,
});
const ROWS = [
  row(),
  row({ faculty_id: 2, employee_code: 'F002', name: 'Prof. Anil Rao', max_hours: 8, assigned_hours: 10, scheduled_hours: 10, overload_hours: 2, status: 'over_limit' }),
  row({ faculty_id: 3, employee_code: 'F003', name: 'Dr. Sunil Das', max_hours: 2, assigned_hours: 3, scheduled_hours: 2, over_assigned_hours: 1, status: 'at_limit' }),
  row({ faculty_id: 4, employee_code: 'F004', name: 'Dr. Kiran Pal', max_hours: 4, assigned_hours: 6, scheduled_hours: 0, over_assigned_hours: 2, status: 'over_assigned' }),
  row({ faculty_id: 5, employee_code: 'F005', name: 'Dr. No Limit', max_hours: null, status: 'no_limit' }),
];

describe('WorkloadTable', () => {
  it('shows scheduled, assigned and maximum hours with a status for every faculty member', () => {
    render(<WorkloadTable rows={ROWS} />);
    const ok = screen.getByRole('row', { name: /Dr\. Meera Rao/ });
    expect(within(ok).getAllByText('10 h')).toHaveLength(2);
    expect(within(ok).getByText('18 h')).toBeInTheDocument();
    expect(within(ok).getByText('Within limit')).toBeInTheDocument();
  });

  it('flags an overload with the number of hours over', () => {
    render(<WorkloadTable rows={ROWS} />);
    const over = screen.getByRole('row', { name: /Prof\. Anil Rao/ });
    expect(within(over).getByText(/Over limit · 2 h over/)).toBeInTheDocument();
    expect(within(over).getByText('8 h')).toBeInTheDocument();
  });

  it('explains a faculty member placed up to the limit with hours that could not be placed', () => {
    render(<WorkloadTable rows={ROWS} />);
    expect(within(screen.getByRole('row', { name: /Dr\. Sunil Das/ })).getByText(/At the limit · 1 h unplaceable/)).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /Dr\. Kiran Pal/ })).getByText(/Assigned over limit · 2 h unplaceable/)).toBeInTheDocument();
  });

  it('says plainly when no limit is configured', () => {
    render(<WorkloadTable rows={ROWS} />);
    const r = screen.getByRole('row', { name: /Dr\. No Limit/ });
    expect(within(r).getByText('Not set')).toBeInTheDocument();
    expect(within(r).getByText('No limit set')).toBeInTheDocument();
  });

  it('shows an empty state without rows', () => {
    render(<WorkloadTable rows={[]} />);
    expect(screen.getByText('No faculty workload')).toBeInTheDocument();
  });
});

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
const timetable = (over = {}) => ({ id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, validated_at: null, generated_at: '2026-10-01T10:00:00', periods: 4, unscheduled_sessions: 0, can_discard: true, ...over });
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });
const renderPage = () => render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
});

describe('Generate dialog - workload', () => {
  function mockApi(preview) {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.startsWith('/timetables/workload-preview')) return preview();
      if (url === '/terms') return Promise.resolve({ items: [{ id: 1, name: 'Autumn 2026', academic_year: '2026-27', is_active: true }] });
      return Promise.reject(new Error(`unexpected ${url}`));
    });
  }
  async function open() {
    renderPage();
    await screen.findByRole('row', { name: /timetable v1/ });
    await userEvent.click(screen.getAllByRole('button', { name: /Generate timetable/ })[0]);
    return screen.findByRole('dialog', { name: 'Generate timetable' });
  }

  it('warns before generating when assignments exceed a weekly limit, and still allows generating', async () => {
    mockApi(() => Promise.resolve({ term_id: 1, workload: [], warnings: ['Dr. Kiran Pal is assigned at least 6 h of teaching per week but the maximum is 4 h (2 h too many).'] }));
    const dialog = await open();
    expect(await within(dialog).findByText(/assigned at least 6 h/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/timetables/workload-preview?term_id=1');
    expect(within(dialog).getByRole('button', { name: 'Generate draft' })).toBeEnabled();
  });

  it('shows no warning when everything fits', async () => {
    mockApi(() => Promise.resolve({ term_id: 1, workload: [], warnings: [] }));
    const dialog = await open();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/timetables/workload-preview?term_id=1'));
    expect(within(dialog).queryByRole('status')).not.toBeInTheDocument();
  });

  it('does not block generation when the preview itself fails', async () => {
    mockApi(() => Promise.reject(new Error('boom')));
    const dialog = await open();
    await waitFor(() => expect(within(dialog).getByLabelText('Term')).toHaveValue('1'));
    expect(within(dialog).getByRole('button', { name: 'Generate draft' })).toBeEnabled();
    expect(within(dialog).queryByText('boom')).not.toBeInTheDocument();
  });

  it('shows the workload table in the generation summary', async () => {
    mockApi(() => Promise.resolve({ term_id: 1, workload: [], warnings: [] }));
    api.post.mockResolvedValue({
      ...timetable({ id: 9, name: 'Autumn 2026 timetable v2', version: 2 }),
      generation: { status: 'partial', required_sessions: 5, scheduled_sessions: 4, unscheduled_sessions: 1, scheduled_periods: 4, unscheduled_reasons: { workload_limit: 1 }, warnings: [], workload: ROWS },
    });
    const dialog = await open();
    await waitFor(() => expect(within(dialog).getByLabelText('Term')).toHaveValue('1'));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Generate draft' }));
    const done = await screen.findByRole('dialog', { name: 'Draft timetable generated' });
    expect(within(done).getByText(/Weekly hour limit: 1/)).toBeInTheDocument();
    expect(within(within(done).getByRole('table', { name: 'Faculty weekly teaching hours' })).getByRole('row', { name: /Dr\. Sunil Das/ })).toBeInTheDocument();
  });
});

describe('Timetable detail - workload', () => {
  const BATCH = { id: 1, name: 'CSE Sem 3 - A' };
  const detail = (workload) => ({ ...timetable(), entries: [], unscheduled: [{ id: 1, assignment_id: 3, session_no: 2, batch: BATCH, subject: { id: 3, code: 'CS303', name: 'Operating Systems' }, faculty: { id: 2, name: 'Prof. Anil Rao' }, reason_code: 'workload_limit', reason_text: 'CS303 would take Prof. Anil Rao to 9 h per week, over the maximum of 8 h.' }], workload });

  async function view(workload) {
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve(listOf([timetable()]));
      if (url.startsWith('/timetables/')) return Promise.resolve(detail(workload));
      if (url.startsWith('/time-slots')) return Promise.resolve({ items: [] });
      return Promise.reject(new Error(`unexpected ${url}`));
    });
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
    return screen.findByRole('heading', { name: 'Faculty workload' });
  }

  it('shows each faculty member against their maximum, including an overload', async () => {
    await view(ROWS);
    const table = screen.getByRole('table', { name: 'Faculty weekly teaching hours' });
    expect(within(within(table).getByRole('row', { name: /Prof\. Anil Rao/ })).getByText(/Over limit · 2 h over/)).toBeInTheDocument();
  });

  it('labels a session left out because of the hour limit', async () => {
    await view(ROWS);
    const row = screen.getByRole('row', { name: /CS303/ });
    expect(within(row).getByText('Weekly hour limit')).toBeInTheDocument();
    expect(within(row).getByText(/over the maximum of 8 h/)).toBeInTheDocument();
  });

  it('shows the empty state when there is no workload', async () => {
    await view([]);
    expect(screen.getByText('No faculty workload')).toBeInTheDocument();
  });
});
