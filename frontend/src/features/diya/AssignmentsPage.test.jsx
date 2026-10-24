import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import AssignmentsPage from './AssignmentsPage.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERMS = { items: [{ id: 1, name: '2026-27 Odd', academic_year: '2026-27', is_active: true }, { id: 2, name: '2025-26 Even', academic_year: '2025-26', is_active: false }] };
const BATCHES = {
  items: [
    { id: 1, name: 'CSE Sem 3 - A', strength: 58, semester_no: 3 },
    { id: 2, name: 'CSE Sem 4 - A', strength: 60, semester_no: 4 },
  ], page: 1, per_page: 100, total: 2, pages: 1,
};
const FACULTY = {
  items: [
    { id: 1, employee_code: 'F001', name: 'Dr. Rakesh Sharma', is_active: true },
    { id: 2, employee_code: 'F002', name: 'Dr. Meera Iyer', is_active: true },
  ], page: 1, per_page: 100, total: 2, pages: 1,
};
const SUBJECTS_3 = { items: [{ id: 10, code: 'CS301', name: 'Data Structures', class_type: 'theory', weekly_hours: 4, lab_block_periods: 2 }, { id: 11, code: 'CS351', name: 'DS Lab', class_type: 'lab', weekly_hours: 4, lab_block_periods: 2 }], total: 2 };
const SUBJECTS_4 = { items: [{ id: 20, code: 'CS401', name: 'Computer Networks', class_type: 'theory', weekly_hours: 3, lab_block_periods: 2 }], total: 1 };

const row = (over = {}) => ({
  id: 1, term: { id: 1, name: '2026-27 Odd', is_active: true },
  batch: { id: 1, name: 'CSE Sem 3 - A', semester_no: 3, strength: 58, department_code: 'CSE' },
  subject: { id: 10, code: 'CS301', name: 'Data Structures', class_type: 'theory', semester_no: 3, weekly_hours: 4, lab_block_periods: 2, department_code: 'CSE' },
  faculty: { id: 1, employee_code: 'F001', name: 'Dr. Rakesh Sharma', is_active: true },
  sessions_per_week: 4, session_length: 1, periods_per_week: 4, cross_department: false, session_mismatch: false, warnings: [],
  usage: { timetable_entries: 0, unscheduled_items: 0 }, in_use: false, ...over,
});
const LAB = row({ id: 2, subject: { id: 11, code: 'CS351', name: 'DS Lab', class_type: 'lab', semester_no: 3, weekly_hours: 4, lab_block_periods: 2, department_code: 'CSE' }, sessions_per_week: 2, session_length: 2, periods_per_week: 4,
  warnings: [{ code: 'no_lab_window', message: 'Dr. Rakesh Sharma has no day with 2 consecutive periods that are not marked unavailable, so this 2-period lab session cannot be placed.' }] });
const LOCKED = row({ id: 3, subject: { id: 12, code: 'CS302', name: 'DBMS', class_type: 'theory', semester_no: 3, weekly_hours: 4, lab_block_periods: 2, department_code: 'ECE' }, cross_department: true, in_use: true, usage: { timetable_entries: 2, unscheduled_items: 0 } });
const ROWS = [row(), LAB, LOCKED];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><AssignmentsPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/teaching-assignments')).at(-1);
const loaded = () => screen.findByRole('row', { name: /CS302/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((path) => {
    if (path === '/terms') return Promise.resolve(TERMS);
    if (path.startsWith('/batches')) return Promise.resolve(BATCHES);
    if (path.startsWith('/faculty')) return Promise.resolve(FACULTY);
    if (path.startsWith('/subjects')) return Promise.resolve(path.includes('semester_no=4') ? SUBJECTS_4 : path.includes('semester_no=3') ? SUBJECTS_3 : { items: [] });
    return Promise.resolve(listOf(ROWS));
  });
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getByRole('button', { name: /Add assignment/ }));
  const dialog = screen.getByRole('dialog', { name: 'Add teaching assignment' });
  await within(dialog).findByRole('option', { name: /CSE Sem 3 - A/ });
  await within(dialog).findByRole('option', { name: /F001/ });
  return dialog;
}

describe('Teaching assignments screen - listing', () => {
  it('shows batch, subject, teacher and the weekly need calculated by the server', async () => {
    renderPage();
    const theory = await screen.findByRole('row', { name: /CS301/ });
    expect(within(theory).getByText('Dr. Rakesh Sharma')).toBeInTheDocument();
    expect(within(theory).getByText('4 periods/week')).toBeInTheDocument();
    expect(within(theory).getByText('Theory')).toBeInTheDocument();
    const lab = screen.getByRole('row', { name: /CS351/ });
    expect(within(lab).getByText('2 × 2 periods (4/week)')).toBeInTheDocument();
    expect(within(lab).getByText('Lab')).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-3 of 3 assignments');
    expect(screen.getByRole('heading', { level: 1, name: 'Teaching assignments' })).toBeInTheDocument();
  });

  it('flags availability warnings, cross-department subjects and assignments that are in a timetable', async () => {
    renderPage();
    await loaded();
    expect(within(screen.getByRole('row', { name: /CS351/ })).getByText('Availability check')).toBeInTheDocument();
    const locked = screen.getByRole('row', { name: /CS302/ });
    expect(within(locked).getByText('Cross-department')).toBeInTheDocument();
    expect(within(locked).getByText('In a timetable')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /CS301/ })).getByText('—')).toBeInTheDocument();
  });

  it('sends batch, faculty, type filters and the search text to the server', async () => {
    renderPage();
    await loaded();
    await screen.findByRole('option', { name: 'CSE Sem 3 - A' });
    await screen.findByRole('option', { name: 'F002 · Dr. Meera Iyer' });
    await userEvent.selectOptions(screen.getByLabelText('Batch'), 'CSE Sem 3 - A');
    await waitFor(() => expect(lastList()).toContain('batch_id=1'));
    await userEvent.selectOptions(screen.getByLabelText('Faculty'), 'F002 · Dr. Meera Iyer');
    await waitFor(() => expect(lastList()).toContain('faculty_id=2'));
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'Lab');
    await waitFor(() => expect(lastList()).toContain('class_type=lab'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search assignments/ }), 'rakesh');
    await waitFor(() => expect(lastList()).toContain('q=rakesh'));
  });

  it('shows empty and error states', async () => {
    api.get.mockImplementation((path) => Promise.resolve(path === '/terms' ? TERMS : path.startsWith('/teaching') ? listOf([]) : path.startsWith('/faculty') ? FACULTY : BATCHES));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No teaching assignments yet' })).toBeInTheDocument();
    unmount();
    api.get.mockImplementation((path) => (path.startsWith('/teaching') ? Promise.reject(new Error('Cannot reach the server.')) : Promise.resolve(path === '/terms' ? TERMS : path.startsWith('/faculty') ? FACULTY : BATCHES)));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('Teaching assignments screen - add', () => {
  it('starts with the active term selected, and the subject list waits for a batch', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByLabelText('Term')).toHaveValue('1');
    expect(within(dialog).getByLabelText('Subject')).toBeDisabled();
    expect(within(dialog).getByText(/Choose a batch first/)).toBeInTheDocument();
    expect(within(dialog).getByRole('option', { name: /2025-26 Even \(inactive\)/ })).toBeInTheDocument();
  });

  it('lists only the subjects of the chosen batch semester, and changing the batch clears an incompatible subject', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '1');
    expect(await within(dialog).findByRole('option', { name: /CS301 · Data Structures/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole('option', { name: /CS401/ })).not.toBeInTheDocument();
    expect(within(dialog).getByText('Showing semester 3 subjects.')).toBeInTheDocument();
    expect(gets()).toContain('/subjects?per_page=100&semester_no=3');
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '10');
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '2');
    expect(await within(dialog).findByRole('option', { name: /CS401/ })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Subject')).toHaveValue('');
  });

  it('shows how many sessions the subject needs, calculated and read-only', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '1');
    await within(dialog).findByRole('option', { name: /CS351/ });
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '11');
    const need = within(dialog).getByRole('status');
    expect(need).toHaveTextContent('2 lab sessions per week');
    expect(need).toHaveTextContent('Each session needs 2 consecutive periods (4 periods per week in total).');
    expect(need).toHaveTextContent('cannot be edited here');
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '10');
    expect(within(dialog).getByRole('status')).toHaveTextContent('4 classes per week');
    expect(within(dialog).queryByLabelText(/sessions/i)).not.toBeInTheDocument(); // no input for the count
  });

  it('reports every missing choice and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create assignment' }));
    expect(await within(dialog).findByText('Choose a batch.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a subject.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a faculty member.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('sends only the four ids, then toasts, closes and reloads', async () => {
    api.post.mockResolvedValue(row({ id: 9 }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '1');
    await within(dialog).findByRole('option', { name: /CS301/ });
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '10');
    await userEvent.selectOptions(within(dialog).getByLabelText('Faculty member'), '1');
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create assignment' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/teaching-assignments', { term_id: 1, batch_id: 1, subject_id: 10, faculty_id: 1 }));
    expect(await screen.findByText('Assignment created')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('turns availability warnings from the server into a visible "Check availability" notice (the assignment is still saved)', async () => {
    api.post.mockResolvedValue(row({ id: 9, warnings: [{ code: 'availability_shortfall', message: 'Dr. Rakesh Sharma is assigned 8 periods per week in this term but only 5 time slots are not marked unavailable.' }] }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '1');
    await within(dialog).findByRole('option', { name: /CS301/ });
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '10');
    await userEvent.selectOptions(within(dialog).getByLabelText('Faculty member'), '1');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create assignment' }));
    expect(await screen.findByText('Assignment created')).toBeInTheDocument();
    expect(await screen.findByText('Check availability')).toBeInTheDocument();
    expect(screen.getByText(/only 5 time slots are not marked unavailable/)).toBeInTheDocument();
  });

  it('shows a duplicate-assignment error from the server on the subject field and keeps the choices', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('CSE Sem 3 - A already has CS301 assigned to Dr. Rakesh Sharma in this term. A batch has one teacher per subject.'), { details: { subject_id: 'This subject is already assigned to that batch in this term.' } }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '1');
    await within(dialog).findByRole('option', { name: /CS301/ });
    await userEvent.selectOptions(within(dialog).getByLabelText('Subject'), '10');
    await userEvent.selectOptions(within(dialog).getByLabelText('Faculty member'), '2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create assignment' }));
    expect(await within(dialog).findByText('This subject is already assigned to that batch in this term.')).toBeInTheDocument();
    expect(within(dialog).getByText(/A batch has one teacher per subject/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Faculty member')).toHaveValue('2');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Teaching assignments screen - edit', () => {
  it('prefills an editable assignment, shows its availability warnings and saves a new teacher', async () => {
    api.patch.mockResolvedValue(LAB);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CS351 for CSE Sem 3 - A' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit teaching assignment' });
    await within(dialog).findByRole('option', { name: /CS351/ });
    expect(within(dialog).getByText('Availability check')).toBeInTheDocument();
    expect(within(dialog).getByText(/no day with 2 consecutive periods/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Subject')).toHaveValue('11');
    expect(within(dialog).getByLabelText('Faculty member')).toBeEnabled();
    await userEvent.selectOptions(within(dialog).getByLabelText('Faculty member'), '2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/teaching-assignments/2', { term_id: 1, batch_id: 1, subject_id: 11, faculty_id: 2 }));
    expect(await screen.findByText('Assignment updated')).toBeInTheDocument();
  });

  it('freezes every field of an assignment that is in a generated timetable', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CS302 for CSE Sem 3 - A' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/A generated timetable uses this assignment/)).toBeInTheDocument();
    ['Term', 'Batch', 'Subject', 'Faculty member'].forEach((label) => expect(within(dialog).getByLabelText(label)).toBeDisabled());
  });
});

describe('Teaching assignments screen - delete', () => {
  it('asks first and explains that the subject, batch and teacher stay as they are', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS301 for CSE Sem 3 - A' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this assignment?' });
    expect(dialog).toHaveTextContent('Dr. Rakesh Sharma will no longer teach CS301 to CSE Sem 3 - A');
    expect(dialog).toHaveTextContent('stay as they are');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS301 for CSE Sem 3 - A' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/teaching-assignments/1'));
    expect(await screen.findByText('Assignment deleted')).toBeInTheDocument();
  });

  it('refuses, with an explanation and no API call, for an assignment that is in a timetable', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS302 for CSE Sem 3 - A' }));
    const dialog = screen.getByRole('dialog', { name: 'This assignment is in a timetable' });
    expect(dialog).toHaveTextContent('Remove or regenerate the timetable first');
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('shows the server message in an error toast if the delete is refused', async () => {
    api.delete.mockRejectedValue(new Error('This assignment is used by 1 timetable entry in a generated timetable and cannot be deleted.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS301 for CSE Sem 3 - A' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete the assignment')).toBeInTheDocument();
    expect(screen.getByText(/cannot be deleted/)).toBeInTheDocument();
  });
});
