import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FacultyTimetablePage, StudentTimetablePage } from './MyTimetablePage.jsx';
import { buildPublishedGrid } from './published.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27', is_active: true };
const SPRING = { id: 2, name: 'Spring 2027', academic_year: '2026-27', is_active: false };
const slot = (day, dayName, period, start, end, type = 'class') => ({ day_of_week: day, day_name: dayName, period_no: period, start_time: start, end_time: end, slot_type: type });
const SLOTS = [
  slot(0, 'Monday', 1, '09:00', '10:00'), slot(0, 'Monday', 2, '10:00', '11:00'), slot(0, 'Monday', 3, '11:00', '12:00', 'break'),
  slot(1, 'Tuesday', 1, '09:00', '10:00'), slot(1, 'Tuesday', 2, '10:00', '11:00'), slot(1, 'Tuesday', 3, '11:00', '12:00', 'break'),
];
const theory = { day_of_week: 0, day_name: 'Monday', period_no: 1, periods: 1, start_time: '09:00', end_time: '10:00', subject: { code: 'CS301', name: 'Data Structures', class_type: 'theory' }, room: { code: 'R201', name: 'Room 201' } };
const lab = { day_of_week: 1, day_name: 'Tuesday', period_no: 1, periods: 2, start_time: '09:00', end_time: '11:00', subject: { code: 'CS351', name: 'DS Lab', class_type: 'lab' }, room: { code: 'LAB1', name: 'Lab 1' } };

const facultyView = (over = {}) => ({
  owner: { name: 'Dr. Rakesh Sharma', employee_code: 'F001' }, term: TERM, terms: [TERM], timetable: { name: 'Autumn 2026 timetable v2', version: 2, published_at: '2026-10-03T09:00:00' }, slots: SLOTS,
  sessions: [{ ...theory, batch: { name: 'CSE Sem 3 - A' } }, { ...lab, batch: { name: 'CSE Sem 3 - B' } }], ...over,
});
const studentView = (over = {}) => ({
  owner: { name: 'Aarav Singh', batch: 'CSE Sem 3 - A' }, term: TERM, terms: [TERM], timetable: { name: 'Autumn 2026 timetable v2', version: 2, published_at: '2026-10-03T09:00:00' }, slots: SLOTS,
  sessions: [{ ...theory, faculty: { name: 'Dr. Rakesh Sharma' } }, { ...lab, faculty: { name: 'Prof. Anil Rao' } }], ...over,
});

const renderFaculty = () => render(<MemoryRouter><FacultyTimetablePage /></MemoryRouter>);
const renderStudent = () => render(<MemoryRouter><StudentTimetablePage /></MemoryRouter>);
const grid = () => screen.getByRole('table', { name: 'Weekly timetable' });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
});

describe('Faculty timetable', () => {
  it('shows my classes with room and batch, from my own endpoint only', async () => {
    api.get.mockResolvedValue(facultyView());
    renderFaculty();
    expect(await screen.findByRole('heading', { level: 1, name: 'My timetable' })).toBeInTheDocument();
    await waitFor(() => expect(within(grid()).getByText(/CS301 · Data Structures/)).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith('/faculty/timetable');
    expect(within(grid()).getByText('Room R201')).toBeInTheDocument();
    expect(within(grid()).getByText('CSE Sem 3 - A')).toBeInTheDocument();
    expect(screen.getByText(/Version 2/)).toBeInTheDocument();
    expect(screen.getByText(/Dr\. Rakesh Sharma · F001/)).toBeInTheDocument();
  });

  it('shows a consecutive lab as one block spanning both periods, and the break', async () => {
    api.get.mockResolvedValue(facultyView());
    renderFaculty();
    const labCell = (await within(await screen.findByRole('table', { name: 'Weekly timetable' })).findByText(/CS351 · DS Lab/)).closest('td');
    expect(labCell).toHaveAttribute('rowspan', '2');
    expect(within(grid()).getAllByText('Break').length).toBeGreaterThan(0);
  });

  it('offers no way to change anything', async () => {
    api.get.mockResolvedValue(facultyView());
    renderFaculty();
    await screen.findByRole('table', { name: 'Weekly timetable' });
    const names = screen.getAllByRole('button').map((b) => b.textContent);
    for (const word of ['Edit', 'Move', 'Validate', 'Generate', 'Approve', 'Publish', 'Reject', 'Discard', 'Submit', 'Delete', 'Save']) {
      expect(names.some((n) => n.includes(word))).toBe(false);
    }
    expect(within(grid()).queryAllByRole('button')).toHaveLength(0);       // classes are plain text, not buttons
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('says when there are no classes in the published timetable', async () => {
    api.get.mockResolvedValue(facultyView({ sessions: [] }));
    renderFaculty();
    expect(await screen.findByText('You have no classes in this timetable.')).toBeInTheDocument();
  });
});

describe('Student timetable', () => {
  it('shows my batch timetable with teachers, from my own endpoint only', async () => {
    api.get.mockResolvedValue(studentView());
    renderStudent();
    await waitFor(() => expect(within(grid()).getByText(/CS301 · Data Structures/)).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledWith('/student/timetable');
    expect(within(grid()).getByText('Dr. Rakesh Sharma')).toBeInTheDocument();
    expect(within(grid()).getByText('Prof. Anil Rao')).toBeInTheDocument();
    expect(screen.getByText(/Aarav Singh · CSE Sem 3 - A/)).toBeInTheDocument();
    expect(within(grid()).queryByText(/CSE Sem 3 - B/)).not.toBeInTheDocument();
  });

  it('has no controls that change data', async () => {
    api.get.mockResolvedValue(studentView());
    renderStudent();
    await screen.findByRole('table', { name: 'Weekly timetable' });
    expect(within(grid()).queryAllByRole('button')).toHaveLength(0);
    expect(screen.queryByRole('link', { name: /edit|publish|generate/i })).not.toBeInTheDocument();
  });
});

describe('States', () => {
  it('shows an accessible loading state first', async () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    renderStudent();
    expect(await screen.findByRole('status')).toHaveTextContent('Loading your timetable…');
  });

  it('explains when nothing is published for the term', async () => {
    api.get.mockResolvedValue(studentView({ timetable: null, slots: [], sessions: [], terms: [] }));
    renderStudent();
    expect(await screen.findByText('No published timetable yet')).toBeInTheDocument();
    expect(screen.getByText(/No timetable has been published for Autumn 2026 yet/)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Weekly timetable' })).not.toBeInTheDocument();
  });

  it('explains when there is no active term', async () => {
    api.get.mockResolvedValue(facultyView({ timetable: null, term: null, terms: [], slots: [], sessions: [] }));
    renderFaculty();
    expect(await screen.findByText(/There is no active term at the moment/)).toBeInTheDocument();
  });

  it('shows the error and retries', async () => {
    api.get.mockRejectedValueOnce(new Error('Server unavailable')).mockResolvedValueOnce(studentView());
    renderStudent();
    expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect((await screen.findAllByText(/CS301 · Data Structures/)).length).toBeGreaterThan(0);  // the week grid and the day list
    expect(screen.queryByText('Server unavailable')).not.toBeInTheDocument();
  });

  it('a profile problem from the server is shown as an error', async () => {
    api.get.mockRejectedValue(new Error('Your account is not linked to a student record. Please contact the administrator.'));
    renderStudent();
    expect(await screen.findByText(/not linked to a student record/)).toBeInTheDocument();
  });
});

describe('Terms', () => {
  it('has no term selector when only one term has a published timetable', async () => {
    api.get.mockResolvedValue(studentView());
    renderStudent();
    await screen.findByRole('table', { name: 'Weekly timetable' });
    expect(screen.queryByLabelText('Term')).not.toBeInTheDocument();
  });

  it('lets me switch between published terms and asks the server for that term', async () => {
    api.get.mockImplementation((url) => Promise.resolve(url.includes('term_id=2')
      ? studentView({ term: SPRING, terms: [SPRING, TERM], timetable: { name: 'Spring v1', version: 1, published_at: null }, sessions: [{ ...theory, faculty: { name: 'Dr. Rakesh Sharma' } }] })
      : studentView({ terms: [SPRING, TERM] })));
    renderStudent();
    const select = await screen.findByLabelText('Term');
    expect(select).toHaveValue('1');
    expect(within(select).getByRole('option', { name: /Autumn 2026 .* · current/ })).toBeInTheDocument();
    await userEvent.selectOptions(select, '2');
    expect(api.get).toHaveBeenLastCalledWith('/student/timetable?term_id=2');
    expect(await screen.findByText(/Spring 2027 · 2026-27/)).toBeInTheDocument();
    expect(screen.getByLabelText('Term')).toHaveValue('2');
  });

  it('points to the other terms when the active one has nothing published', async () => {
    api.get.mockResolvedValue(studentView({ timetable: null, slots: [], sessions: [], terms: [SPRING, { ...TERM, id: 3, name: 'Autumn 2025', is_active: false }] }));
    renderStudent();
    expect(await screen.findByText(/You can choose another term above/)).toBeInTheDocument();
    const select = screen.getByLabelText('Term');
    expect(within(select).getByRole('option', { name: /Autumn 2026 \(nothing published\)/ })).toBeInTheDocument();
  });
});

describe('buildPublishedGrid', () => {
  it('builds days, periods (with the break) and spanning entries', () => {
    const g = buildPublishedGrid(facultyView(), 'faculty');
    expect(g.days.map((d) => d.label)).toEqual(['Mon', 'Tue']);
    expect(g.periods.map((p) => p.kind)).toEqual(['class', 'class', 'break']);
    expect(g.entries.find((e) => e.kind === 'lab')).toMatchObject({ dayKey: 1, periodKey: 1, span: 2, lines: ['Room LAB1', 'CSE Sem 3 - B'] });
    expect(buildPublishedGrid(studentView(), 'student').entries[0].lines).toEqual(['Room R201', 'Dr. Rakesh Sharma']);
  });
});
