import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import BatchesPage from './BatchesPage.jsx';
import { usageSentence, validateBatch } from './batches.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const DEPARTMENTS = { items: [{ id: 1, code: 'CSE', name: 'Computer Science' }] };
const PROGRAMS = { items: [{ id: 1, name: 'B.Tech CSE', duration_semesters: 8, department: { id: 1, code: 'CSE', name: 'Computer Science' } }] };
const batch = (over = {}) => ({
  id: 1, name: 'CSE Sem 3 - A', section: 'A', semester_no: 3, strength: 58, student_count: 2, seats_left: 56,
  program: { id: 1, name: 'B.Tech CSE', duration_semesters: 8 }, department: { id: 1, code: 'CSE', name: 'Computer Science' },
  usage: { students: 2, teaching_assignments: 6, timetable_entries: 0, announcements: 0 }, in_use: true, scheduled: true, ...over,
});
const FREE = batch({ id: 3, name: 'CSE Sem 4 - A', semester_no: 4, strength: 60, student_count: 0, seats_left: 60, usage: { students: 0, teaching_assignments: 0, timetable_entries: 0, announcements: 0 }, in_use: false, scheduled: false });
const WITH_STUDENTS = batch({ id: 4, name: 'CSE Sem 5 - A', semester_no: 5, student_count: 3, scheduled: false, usage: { students: 3, teaching_assignments: 0, timetable_entries: 0, announcements: 1 } });
const BATCHES = [batch(), batch({ id: 2, name: 'CSE Sem 3 - B', section: 'B', strength: 42, student_count: 42, seats_left: 0 }), FREE, WITH_STUDENTS];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><BatchesPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/batches')).at(-1);
const loaded = () => screen.findByRole('row', { name: /CSE Sem 4 - A/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : path === '/programs' ? PROGRAMS : listOf(BATCHES)));
});

async function openCreate() {
  await loaded();
  await screen.findByRole('option', { name: 'CSE' });
  await userEvent.click(screen.getByRole('button', { name: /Add batch/ }));
  const dialog = screen.getByRole('dialog', { name: 'Add batch' });
  await within(dialog).findByRole('option', { name: 'B.Tech CSE · CSE' });
  return dialog;
}

describe('Batches screen - listing', () => {
  it('shows each batch with enrolled / strength, a labelled progress bar and timetable status', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /CSE Sem 3 - A/ });
    expect(within(row).getByText('B.Tech CSE')).toBeInTheDocument();
    expect(row).toHaveTextContent('2 / 58');
    expect(within(row).getByRole('img', { name: '2 of 58 places filled' })).toBeInTheDocument();
    expect(within(row).getByText('Scheduled')).toBeInTheDocument();
    const full = screen.getByRole('row', { name: /CSE Sem 3 - B/ });
    expect(within(full).getByRole('img', { name: '42 of 42 places filled' })).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /CSE Sem 4 - A/ })).getByText('Not scheduled')).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-4 of 4 batches');
    expect(screen.getByRole('heading', { level: 1, name: 'Batches' })).toBeInTheDocument();
  });

  it('sends department, semester and search to the server', async () => {
    renderPage();
    await loaded();
    await screen.findByRole('option', { name: 'CSE' });
    await userEvent.selectOptions(screen.getByLabelText('Department'), 'CSE');
    await waitFor(() => expect(lastList()).toContain('department_id=1'));
    await userEvent.selectOptions(screen.getByLabelText('Semester'), 'Semester 3');
    await waitFor(() => expect(lastList()).toContain('semester_no=3'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search batches/ }), 'B');
    await waitFor(() => expect(lastList()).toContain('q=B'));
  });

  it('shows empty and error states', async () => {
    api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : path === '/programs' ? PROGRAMS : listOf([])));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No batches yet' })).toBeInTheDocument();
    unmount();
    api.get.mockImplementation((path) => (path.startsWith('/batches') ? Promise.reject(new Error('Cannot reach the server.')) : Promise.resolve(path === '/programs' ? PROGRAMS : DEPARTMENTS)));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('Batches screen - create (DIY-TC04)', () => {
  it('reports every missing field and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create batch' }));
    expect(await within(dialog).findByText('Choose a program.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 1 to 12.')).toBeInTheDocument();
    expect(within(dialog).getByText('Use 1 to 10 letters or digits, e.g. A.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 1 to 500.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("limits the semester to the selected program's duration", async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Program'), '1');
    await userEvent.type(within(dialog).getByLabelText('Semester'), '9');
    await userEvent.type(within(dialog).getByLabelText('Section'), 'A');
    await userEvent.type(within(dialog).getByLabelText('Batch strength'), '60');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create batch' }));
    expect(await within(dialog).findByText('B.Tech CSE has 8 semesters. Enter a number from 1 to 8.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('sends a valid batch, then toasts, closes and reloads', async () => {
    api.post.mockResolvedValue(batch({ id: 9, name: 'CSE Sem 4 - C' }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Program'), '1');
    await userEvent.type(within(dialog).getByLabelText('Semester'), '4');
    await userEvent.type(within(dialog).getByLabelText('Section'), 'c');
    await userEvent.type(within(dialog).getByLabelText('Batch strength'), '55');
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create batch' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/batches', { program_id: 1, semester_no: 4, section: 'c', strength: 55, name: '' }));
    expect(await screen.findByText('Batch created')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('shows a duplicate section error from the server on the field and keeps the entered data', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('Section A of semester 4 already exists for this program.'), { details: { section: 'This section already exists for that program and semester.' } }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Program'), '1');
    await userEvent.type(within(dialog).getByLabelText('Semester'), '4');
    await userEvent.type(within(dialog).getByLabelText('Section'), 'A');
    await userEvent.type(within(dialog).getByLabelText('Batch strength'), '60');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create batch' }));
    expect(await within(dialog).findByText('This section already exists for that program and semester.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Batch strength')).toHaveValue(60);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Batches screen - edit and strength accuracy', () => {
  it('will not accept a strength below the students already in the batch (checked before sending)', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE Sem 5 - A' })); // 3 students
    const dialog = screen.getByRole('dialog', { name: 'Edit CSE Sem 5 - A' });
    expect(within(dialog).getByText(/At least 3/)).toBeInTheDocument();
    const strength = within(dialog).getByLabelText('Batch strength');
    await userEvent.clear(strength);
    await userEvent.type(strength, '2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    expect(await within(dialog).findByText('Cannot be less than the 3 students already in this batch.')).toBeInTheDocument();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it('saves a larger strength', async () => {
    api.patch.mockResolvedValue(FREE);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE Sem 4 - A' }));
    const dialog = screen.getByRole('dialog');
    const strength = within(dialog).getByLabelText('Batch strength');
    await userEvent.clear(strength);
    await userEvent.type(strength, '70');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/batches/3', expect.objectContaining({ strength: 70, semester_no: 4, program_id: 1 })));
    expect(await screen.findByText('Batch updated')).toBeInTheDocument();
  });

  it('locks program and semester for a scheduled batch but not strength or name', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE Sem 3 - A' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/program and semester are locked/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Program')).toBeDisabled();
    expect(within(dialog).getByLabelText('Semester')).toBeDisabled();
    expect(within(dialog).getByLabelText('Batch strength')).toBeEnabled();
    expect(within(dialog).getByLabelText('Section')).toBeEnabled();
  });

  it('shows the server message when it refuses a strength change', async () => {
    api.patch.mockRejectedValue(Object.assign(new Error('This batch already has 3 student records, so its strength cannot be less than 3.'), { details: { strength: 'Cannot be less than the 3 students already in this batch.' } }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE Sem 4 - A' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Save changes' }));
    expect(await within(screen.getByRole('dialog')).findByText(/cannot be less than 3/)).toBeInTheDocument();
  });
});

describe('Batches screen - delete', () => {
  it('deletes an empty unused batch after confirmation', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE Sem 4 - A' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Delete this batch?' })).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/batches/3'));
    expect(await screen.findByText('Batch deleted')).toBeInTheDocument();
  });

  it('explains what uses a batch (students, assignments, announcements) and never calls the API', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE Sem 5 - A' }));
    const dialog = screen.getByRole('dialog', { name: 'This batch is in use' });
    expect(dialog).toHaveTextContent('3 students, 1 announcement');
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
    expect(api.delete).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE Sem 3 - A' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('2 students, 6 teaching assignments');
  });
});

describe('batch form rules (unit)', () => {
  const ok = { program_id: '1', semester_no: '3', section: 'A', strength: '60', name: '' };
  const program = { name: 'B.Tech CSE', duration_semesters: 8 };

  it('accepts a valid batch', () => expect(validateBatch(ok, { program })).toEqual({}));

  it.each([
    [{ program_id: '' }, 'program_id'], [{ semester_no: '9' }, 'semester_no'], [{ semester_no: '0' }, 'semester_no'], [{ section: 'A B' }, 'section'],
    [{ section: '' }, 'section'], [{ strength: '0' }, 'strength'], [{ strength: '501' }, 'strength'], [{ strength: '2.5' }, 'strength'], [{ name: 'x' }, 'name'],
  ])('flags %j', (over, field) => expect(validateBatch({ ...ok, ...over }, { program })).toHaveProperty(field));

  it('enforces the minimum strength from enrolled students', () => {
    expect(validateBatch({ ...ok, strength: '2' }, { program, minStrength: 3 })).toHaveProperty('strength');
    expect(validateBatch({ ...ok, strength: '3' }, { program, minStrength: 3 })).toEqual({});
  });

  it('summarises usage in plain words', () => {
    expect(usageSentence({ students: 1, teaching_assignments: 0, timetable_entries: 2, announcements: 0 })).toBe('1 student, 2 timetable entries');
  });
});
