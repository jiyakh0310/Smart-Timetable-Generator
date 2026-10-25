import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import ExportButtons from './ExportButtons.jsx';
import { FacultyTimetablePage, StudentTimetablePage } from './MyTimetablePage.jsx';
import TimetablesPage from './TimetablesPage.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn(), download: vi.fn() };
vi.mock('../../services/api.js', () => ({
  api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a), download: (...a) => api.download(...a) },
}));
const saveBlob = vi.fn();
vi.mock('../../services/download.js', () => ({ saveBlob: (...a) => saveBlob(...a) }));

const FILE = { blob: new Blob(['x']), filename: 'timetable-demo.pdf' };

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  saveBlob.mockReset();
});

describe('ExportButtons', () => {
  it('offers two labelled buttons in a named group', () => {
    render(<ExportButtons path="/student/timetable/export" />);
    const group = screen.getByRole('group', { name: 'Export this timetable' });
    expect(within(group).getByRole('button', { name: 'Export PDF' })).toBeEnabled();
    expect(within(group).getByRole('button', { name: 'Export Excel' })).toBeEnabled();
  });

  it('downloads the PDF through the authenticated helper and saves it', async () => {
    api.download.mockResolvedValue(FILE);
    render(<ExportButtons path="/student/timetable/export" />);
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    expect(api.download).toHaveBeenCalledWith('/student/timetable/export?format=pdf');
    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(FILE.blob, 'timetable-demo.pdf'));
    expect(await screen.findByText('timetable-demo.pdf was downloaded.')).toBeInTheDocument();
  });

  it('asks for Excel with the chosen term', async () => {
    api.download.mockResolvedValue({ blob: new Blob(['y']), filename: 'timetable.xlsx' });
    render(<ExportButtons path="/faculty/timetable/export" termId={7} />);
    await userEvent.click(screen.getByRole('button', { name: 'Export Excel' }));
    expect(api.download).toHaveBeenCalledWith('/faculty/timetable/export?format=xlsx&term_id=7');
  });

  it('shows loading feedback and blocks a second click while a file is being made', async () => {
    let finish;
    api.download.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<ExportButtons path="/student/timetable/export" />);
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Export Excel' })).toBeDisabled();
    expect(api.download).toHaveBeenCalledTimes(1);
    finish(FILE);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export Excel' })).toBeEnabled());
  });

  it('shows the server error and allows trying again, saving nothing', async () => {
    api.download.mockRejectedValueOnce(new Error('No timetable has been published for Autumn 2026 yet, so there is nothing to export.')).mockResolvedValueOnce(FILE);
    render(<ExportButtons path="/student/timetable/export" />);
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    expect(await screen.findByText(/nothing to export/)).toBeInTheDocument();
    expect(saveBlob).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/nothing to export/)).not.toBeInTheDocument();
  });

  it('can be disabled', () => {
    render(<ExportButtons path="/x" disabled />);
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled();
  });
});

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27', is_active: true };
const slots = [{ day_of_week: 0, day_name: 'Monday', period_no: 1, start_time: '09:00', end_time: '10:00', slot_type: 'class' }];
const session = { day_of_week: 0, day_name: 'Monday', period_no: 1, periods: 1, start_time: '09:00', end_time: '10:00', subject: { code: 'CS301', name: 'DS', class_type: 'theory' }, room: { code: 'R1', name: 'Room' } };
const view = (over = {}) => ({ owner: { name: 'A', employee_code: 'F001', batch: 'B' }, term: TERM, terms: [TERM], timetable: { name: 'v1', version: 1, published_at: null }, slots, sessions: [{ ...session, batch: { name: 'B' }, faculty: { name: 'T' } }], ...over });

describe('Export on the faculty and student screens', () => {
  it.each([['faculty', FacultyTimetablePage, '/faculty/timetable/export'], ['student', StudentTimetablePage, '/student/timetable/export']])('%s screen exports its own endpoint only', async (_who, Page, path) => {
    api.get.mockResolvedValue(view());
    api.download.mockResolvedValue(FILE);
    render(<MemoryRouter><Page /></MemoryRouter>);
    await userEvent.click(await screen.findByRole('button', { name: 'Export PDF' }));
    expect(api.download).toHaveBeenCalledWith(`${path}?format=pdf`);
    expect(api.download.mock.calls.every((c) => !/batch_id|faculty_id|student_id/.test(c[0]))).toBe(true);
  });

  it('exports the term the user picked', async () => {
    const SPRING = { id: 2, name: 'Spring 2027', academic_year: '2026-27', is_active: false };
    api.get.mockImplementation((url) => Promise.resolve(url.includes('term_id=2') ? view({ term: SPRING, terms: [SPRING, TERM] }) : view({ terms: [SPRING, TERM] })));
    api.download.mockResolvedValue(FILE);
    render(<MemoryRouter><StudentTimetablePage /></MemoryRouter>);
    await userEvent.selectOptions(await screen.findByLabelText('Term'), '2');
    await screen.findByText(/Spring 2027 · 2026-27/);
    await userEvent.click(screen.getByRole('button', { name: 'Export Excel' }));
    expect(api.download).toHaveBeenCalledWith('/student/timetable/export?format=xlsx&term_id=2');
  });

  it('offers no export when nothing is published', async () => {
    api.get.mockResolvedValue(view({ timetable: null, slots: [], sessions: [], terms: [] }));
    render(<MemoryRouter><StudentTimetablePage /></MemoryRouter>);
    await screen.findByText('No published timetable yet');
    expect(screen.queryByRole('button', { name: /Export/ })).not.toBeInTheDocument();
  });

  it('the controls are real buttons reachable by keyboard', async () => {
    api.get.mockResolvedValue(view());
    api.download.mockResolvedValue(FILE);
    render(<MemoryRouter><StudentTimetablePage /></MemoryRouter>);
    const button = await screen.findByRole('button', { name: 'Export PDF' });
    button.focus();
    await userEvent.keyboard('{Enter}');
    expect(api.download).toHaveBeenCalledTimes(1);
  });
});

describe('Export on the admin timetable detail', () => {
  it('exports the opened timetable in either format', async () => {
    const t = { id: 5, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, validated_at: null, generated_at: '2026-10-01T10:00:00', periods: 0, unscheduled_sessions: 0, can_discard: true, can_edit: true, allowed_actions: ['submit'], is_current_published: false, approved_at: null, published_at: null, rejection_reason: null };
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve({ items: [t], page: 1, per_page: 10, total: 1, pages: 1 });
      if (url.startsWith('/timetables/')) return Promise.resolve({ ...t, entries: [], unscheduled: [], workload: [] });
      return Promise.resolve({ items: [] });
    });
    api.download.mockResolvedValue(FILE);
    render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
    await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
    await userEvent.click(await screen.findByRole('button', { name: 'Export Excel' }));
    expect(api.download).toHaveBeenCalledWith('/timetables/5/export?format=xlsx');
    await userEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
    expect(api.download).toHaveBeenLastCalledWith('/timetables/5/export?format=pdf');
  });
});
