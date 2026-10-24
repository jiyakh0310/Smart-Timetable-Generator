import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import StudentsPage from './StudentsPage.jsx';
import { validateStudent } from './students.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const batchRow = (id, name, strength, count) => ({ id, name, strength, student_count: count, seats_left: Math.max(strength - count, 0) });
const BATCH_A = batchRow(1, 'CSE Sem 3 - A', 58, 2);
const BATCH_B = batchRow(2, 'CSE Sem 3 - B', 42, 42); // full
const BATCH_C = batchRow(3, 'CSE Sem 4 - A', 1, 0); // exactly one place
const BATCHES = { items: [BATCH_A, BATCH_B, BATCH_C], page: 1, per_page: 100, total: 3, pages: 1 };

const student = (over = {}) => ({
  id: 1, enrollment_no: 'CSE23001', name: 'Aarav Singh', email: 'student1@timetable.test', has_login: true,
  batch: { id: 1, name: 'CSE Sem 3 - A', semester_no: 3, section: 'A', department_code: 'CSE' }, ...over,
});
const STUDENTS = [student(), student({ id: 2, enrollment_no: 'CSE23041', name: 'Rohan Das', email: null, has_login: false, batch: { id: 2, name: 'CSE Sem 3 - B', semester_no: 3, section: 'B', department_code: 'CSE' } })];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><StudentsPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/students')).at(-1);
const loaded = () => screen.findByRole('row', { name: /CSE23041/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((path) => Promise.resolve(path.startsWith('/batches') ? BATCHES : listOf(STUDENTS)));
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getByRole('button', { name: /Add student/ }));
  const dialog = screen.getByRole('dialog', { name: 'Add student' });
  await within(dialog).findByRole('option', { name: /CSE Sem 3 - A/ });
  return dialog;
}
async function fill(dialog, over = {}) {
  const v = { number: 'cse23100', name: 'Meera Joshi', email: 'Meera@College.test', batch: '1', ...over };
  await userEvent.type(within(dialog).getByLabelText('Enrollment number'), v.number);
  await userEvent.type(within(dialog).getByLabelText('Full name'), v.name);
  if (v.email) await userEvent.type(within(dialog).getByLabelText('Email (optional)'), v.email);
  await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), v.batch);
}

describe('Students screen - listing', () => {
  it('shows students with batch and login status, and says it is admin-only', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /CSE23001/ });
    expect(within(row).getByText('Aarav Singh')).toBeInTheDocument();
    expect(within(row).getByText('CSE Sem 3 - A')).toBeInTheDocument();
    expect(within(row).getByText('Has login')).toBeInTheDocument();
    const second = screen.getByRole('row', { name: /CSE23041/ });
    expect(within(second).getByText('No login')).toBeInTheDocument();
    expect(within(second).getByText('—')).toBeInTheDocument(); // no email
    expect(screen.getByText(/Only administrators can see this list/)).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-2 of 2 students');
    expect(lastList()).toBe('/students?page=1&per_page=10');
  });

  it('filters by batch and semester and searches by number, name or email', async () => {
    renderPage();
    await loaded();
    await screen.findByRole('option', { name: 'CSE Sem 3 - B' });
    await userEvent.selectOptions(screen.getByLabelText('Batch'), 'CSE Sem 3 - B');
    await waitFor(() => expect(lastList()).toContain('batch_id=2'));
    await userEvent.selectOptions(screen.getByLabelText('Semester'), 'Semester 3');
    await waitFor(() => expect(lastList()).toContain('semester_no=3'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search students/ }), 'rohan');
    await waitFor(() => expect(lastList()).toContain('q=rohan'));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(lastList()).toBe('/students?page=1&per_page=10'));
  });

  it('shows an empty state and an error state with retry', async () => {
    api.get.mockImplementation((path) => Promise.resolve(path.startsWith('/batches') ? BATCHES : listOf([])));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No students yet' })).toBeInTheDocument();
    unmount();
    api.get.mockImplementation((path) => (path.startsWith('/students') ? Promise.reject(new Error('Cannot reach the server.')) : Promise.resolve(BATCHES)));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    api.get.mockImplementation((path) => Promise.resolve(path.startsWith('/batches') ? BATCHES : listOf(STUDENTS)));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await loaded()).toBeInTheDocument();
  });
});

describe('Students screen - add (DIY-TC01, TC03)', () => {
  it('offers batches with remaining places, and disables full ones', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByRole('option', { name: 'CSE Sem 3 - A · 56 places left' })).toBeEnabled();
    expect(within(dialog).getByRole('option', { name: 'CSE Sem 4 - A · 1 place left' })).toBeEnabled();
    expect(within(dialog).getByRole('option', { name: 'CSE Sem 3 - B · full' })).toBeDisabled();
    expect(within(dialog).getByLabelText('Enrollment number')).toHaveFocus();
  });

  it('DIY-TC03: blocks a form with no enrollment number, name or batch, and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    expect(await within(dialog).findByText('Enter the enrollment number, e.g. CSE23001.')).toBeInTheDocument();
    expect(within(dialog).getByText("Enter the student's name.")).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a batch.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects an invalid email', async () => {
    renderPage();
    const dialog = await openCreate();
    await fill(dialog, { email: 'not-an-email' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    expect(await within(dialog).findByText(/Enter a valid email address/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('DIY-TC01: sends a valid student assigned to the chosen batch, then toasts, closes and reloads', async () => {
    api.post.mockResolvedValue(student({ id: 9, enrollment_no: 'CSE23100', name: 'Meera Joshi' }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog);
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/students', { enrollment_no: 'cse23100', name: 'Meera Joshi', email: 'Meera@College.test', batch_id: 1 }));
    expect(await screen.findByText('Student added')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('sends a null email when the optional field is left empty', async () => {
    api.post.mockResolvedValue(student());
    renderPage();
    const dialog = await openCreate();
    await fill(dialog, { email: '' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/students', expect.objectContaining({ email: null })));
  });

  it('shows a duplicate enrollment number error from the server on the field', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('A student with enrollment number CSE23100 already exists.'), { details: { enrollment_no: 'This enrollment number is already used.' } }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    expect(await within(dialog).findByText('This enrollment number is already used.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Full name')).toHaveValue('Meera Joshi');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows the batch-full message from the server if a batch filled up while the form was open', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('CSE Sem 4 - A is full (1 of 1 places). Increase the batch strength first, or choose another batch.'), { details: { batch_id: 'This batch is full.' } }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog, { batch: '3' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add student' }));
    expect(await within(dialog).findByText('This batch is full.')).toBeInTheDocument();
    expect(within(dialog).getByText(/Increase the batch strength first/)).toBeInTheDocument();
  });

  it('warns if the batch list could not be loaded', async () => {
    api.get.mockImplementation((path) => (path.startsWith('/batches') ? Promise.reject(new Error('Batches unavailable')) : Promise.resolve(listOf(STUDENTS))));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Add student/ }));
    expect(await screen.findByText(/Could not load the batch list: Batches unavailable/)).toBeInTheDocument();
  });
});

describe('Students screen - edit (DIY-TC02)', () => {
  it('prefills the record and saves a changed email and batch', async () => {
    api.patch.mockResolvedValue(student());
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE23001 Aarav Singh' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit CSE23001' });
    await within(dialog).findByRole('option', { name: /CSE Sem 4 - A/ });
    expect(within(dialog).getByLabelText('Full name')).toHaveValue('Aarav Singh');
    expect(within(dialog).getByLabelText('Batch')).toHaveValue('1');
    const email = within(dialog).getByLabelText('Email (optional)');
    await userEvent.clear(email);
    await userEvent.type(email, 'aarav.new@college.test');
    await userEvent.selectOptions(within(dialog).getByLabelText('Batch'), '3');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/students/1', { enrollment_no: 'CSE23001', name: 'Aarav Singh', email: 'aarav.new@college.test', batch_id: 3 }));
    expect(await screen.findByText('Student updated')).toBeInTheDocument();
  });

  it("keeps the student's own batch selectable even when that batch is full", async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CSE23041 Rohan Das' })); // in the full batch B
    const dialog = screen.getByRole('dialog');
    const option = await within(dialog).findByRole('option', { name: 'CSE Sem 3 - B · full' });
    expect(option).toBeEnabled();
    expect(within(dialog).getByLabelText('Batch')).toHaveValue('2');
  });
});

describe('Students screen - delete', () => {
  it('warns that the login will be disabled, and confirms with a toast', async () => {
    api.delete.mockResolvedValue({ login_disabled: true });
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE23001 Aarav Singh' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this student?' });
    expect(dialog).toHaveTextContent('login account will also be disabled');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/students/1'));
    expect(await screen.findByText('Student deleted')).toBeInTheDocument();
    expect(screen.getByText(/their login account was disabled/)).toBeInTheDocument();
  });

  it('does not mention a login for a student without one, and Cancel changes nothing', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE23041 Rohan Das' }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).not.toHaveTextContent('login');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the server message in an error toast if the delete fails', async () => {
    api.delete.mockRejectedValue(new Error('Student not found.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CSE23041 Rohan Das' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete the student')).toBeInTheDocument();
    expect(screen.getByText('Student not found.')).toBeInTheDocument();
  });
});

describe('student form rules (unit)', () => {
  const ok = { enrollment_no: 'CSE23001', name: 'Aarav Singh', email: '', batch_id: '1' };

  it('accepts a valid student, with or without email', () => {
    expect(validateStudent(ok)).toEqual({});
    expect(validateStudent({ ...ok, email: 'a@b.co' })).toEqual({});
    expect(validateStudent({ ...ok, enrollment_no: ' cse-23.001 ' })).toEqual({});
  });

  it.each([
    [{ enrollment_no: '' }, 'enrollment_no'], [{ enrollment_no: 'bad id!' }, 'enrollment_no'], [{ enrollment_no: 'A'.repeat(31) }, 'enrollment_no'],
    [{ name: '' }, 'name'], [{ name: 'x' }, 'name'], [{ name: 'n'.repeat(121) }, 'name'],
    [{ email: 'nope' }, 'email'], [{ email: 'a@b' }, 'email'], [{ batch_id: '' }, 'batch_id'],
  ])('flags %j', (over, field) => expect(validateStudent({ ...ok, ...over })).toHaveProperty(field));
});
