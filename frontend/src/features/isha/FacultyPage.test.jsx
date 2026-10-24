import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import FacultyPage from './FacultyPage.jsx';
import { passwordProblem } from './faculty.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const DEPARTMENTS = { items: [{ id: 1, code: 'CSE', name: 'Computer Science' }] };
const fac = (over = {}) => ({
  id: 1, employee_code: 'F001', name: 'Dr. Rakesh Sharma', email: 'faculty1@timetable.test', department: { id: 1, code: 'CSE', name: 'Computer Science' }, designation: 'Professor',
  max_weekly_hours: 18, is_active: true, last_login: null, usage: { teaching_assignments: 3, timetable_entries: 0 }, in_use: true, availability: { unavailable: 0, preferred: 0 }, ...over,
});
const FREE = fac({ id: 2, employee_code: 'F100', name: 'Dr. Priya Menon', email: 'priya@college.test', designation: null, usage: { teaching_assignments: 0, timetable_entries: 0 }, in_use: false, availability: { unavailable: 2, preferred: 1 } });
const INACTIVE = fac({ id: 3, employee_code: 'F200', name: 'Prof. Old Hand', email: 'old@college.test', is_active: false });
const FACULTY = [fac(), FREE, INACTIVE];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><FacultyPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/faculty')).at(-1);
const loaded = () => screen.findByRole('row', { name: /F200/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : listOf(FACULTY)));
});

async function openCreate() {
  await loaded();
  await screen.findByRole('option', { name: 'CSE' });
  await userEvent.click(screen.getByRole('button', { name: /Add faculty member/ }));
  const dialog = screen.getByRole('dialog', { name: 'Add faculty member' });
  await within(dialog).findByRole('option', { name: /CSE · Computer Science/ });
  return dialog;
}
async function fillCreate(dialog, over = {}) {
  const v = { name: 'Dr. Priya Menon', email: 'priya@college.test', code: 'f100', password: 'Secure#Pass42', ...over };
  await userEvent.type(within(dialog).getByLabelText('Full name'), v.name);
  await userEvent.type(within(dialog).getByLabelText('Login email'), v.email);
  await userEvent.type(within(dialog).getByLabelText('Employee code'), v.code);
  await userEvent.selectOptions(within(dialog).getByLabelText('Department'), '1');
  if (v.password) await userEvent.type(within(dialog).getByLabelText('Initial password'), v.password);
}

describe('Faculty screen - listing', () => {
  it('shows faculty with department, teaching load, availability summary and account status', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /F001/ });
    expect(within(row).getByText('Dr. Rakesh Sharma')).toBeInTheDocument();
    expect(within(row).getByText('faculty1@timetable.test')).toBeInTheDocument();
    expect(within(row).getByText('18 h')).toBeInTheDocument();
    expect(within(row).getByText('3 assignments')).toBeInTheDocument();
    expect(within(row).getByText('Fully available')).toBeInTheDocument();
    expect(within(row).getByText('Active')).toBeInTheDocument();
    const free = screen.getByRole('row', { name: /F100/ });
    expect(within(free).getByText('2 unavailable · 1 preferred')).toBeInTheDocument();
    expect(within(free).getByText('None')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /F200/ })).getByText('Inactive')).toBeInTheDocument();
    expect(within(free).getByRole('link', { name: 'Availability of Dr. Priya Menon' })).toHaveAttribute('href', '/admin/availability?faculty=2');
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-3 of 3 faculty members');
    expect(screen.getByText(/Only administrators can see this list/)).toBeInTheDocument();
  });

  it('never shows or requests password information in the list', async () => {
    const { container } = renderPage();
    await loaded();
    expect(container.textContent).not.toMatch(/password|hash/i);
  });

  it('sends department and status filters and the search text', async () => {
    renderPage();
    await loaded();
    await screen.findByRole('option', { name: 'CSE' });
    await userEvent.selectOptions(screen.getByLabelText('Department'), 'CSE');
    await waitFor(() => expect(lastList()).toContain('department_id=1'));
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Inactive');
    await waitFor(() => expect(lastList()).toContain('active=false'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search faculty/ }), 'priya');
    await waitFor(() => expect(lastList()).toContain('q=priya'));
  });

  it('shows empty and error states', async () => {
    api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : listOf([])));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No faculty members yet' })).toBeInTheDocument();
    unmount();
    api.get.mockImplementation((path) => (path.startsWith('/faculty') ? Promise.reject(new Error('Cannot reach the server.')) : Promise.resolve(DEPARTMENTS)));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});

describe('Faculty screen - add (ISH-TC05, TC08)', () => {
  it('opens with focus on the first field and explains that a login is created', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByLabelText('Full name')).toHaveFocus();
    expect(within(dialog).getByText(/also creates their login account \(role: faculty\)/)).toBeInTheDocument();
    expect(within(dialog).queryByLabelText('Account active')).not.toBeInTheDocument();
  });

  it('ISH-TC08: an empty form reports every required field and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add faculty member' }));
    expect(await within(dialog).findByText("Enter the faculty member's name.")).toBeInTheDocument();
    expect(within(dialog).getByText('Enter the login email address.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter the employee code, e.g. F001.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a department.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a password.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it.each([['short1', /8 to 128/], ['onlyletters', /letter and one number/]])('rejects the weak password %s before sending', async (password, message) => {
    renderPage();
    const dialog = await openCreate();
    await fillCreate(dialog, { password });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add faculty member' }));
    expect(await within(dialog).findByText(message)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects a password identical to the email (it has letters, a digit and enough length, so only that rule can fire)', async () => {
    renderPage();
    const dialog = await openCreate();
    await fillCreate(dialog, { email: 'priya2024@college.test', password: 'priya2024@college.test' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add faculty member' }));
    expect(await within(dialog).findByText(/must not be the same as the email, employee code or name/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('the password is hidden by default, can be shown, and Generate fills a policy-compliant one and reveals it', async () => {
    renderPage();
    const dialog = await openCreate();
    const field = within(dialog).getByLabelText('Initial password');
    expect(field).toHaveAttribute('type', 'password');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Generate secure password' }));
    expect(field).toHaveAttribute('type', 'text');
    expect(passwordProblem(field.value)).toBe('');
    expect(field.value).toHaveLength(14);
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Show' }));
    expect(field).toHaveAttribute('type', 'password');
  });

  it('ISH-TC05: sends the details and password (never a role), then toasts, closes and reloads', async () => {
    api.post.mockResolvedValue(FREE);
    renderPage();
    const dialog = await openCreate();
    await fillCreate(dialog);
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add faculty member' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/faculty', {
      name: 'Dr. Priya Menon', email: 'priya@college.test', employee_code: 'f100', department_id: 1, designation: null, max_weekly_hours: 18, password: 'Secure#Pass42',
    }));
    expect(Object.keys(api.post.mock.calls[0][1])).not.toContain('role');
    expect(await screen.findByText('Faculty member added')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('shows a duplicate email error from the server on the field and keeps the entered data', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('Another account already uses this email address.'), { details: { email: 'This email is already used by another account.' } }));
    renderPage();
    const dialog = await openCreate();
    await fillCreate(dialog);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add faculty member' }));
    expect(await within(dialog).findByText('This email is already used by another account.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Full name')).toHaveValue('Dr. Priya Menon');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Faculty screen - edit, deactivate, reset password (ISH-TC06)', () => {
  it('prefills the record, has no password field, and saves changes including the active flag', async () => {
    api.patch.mockResolvedValue(FREE);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit F100 Dr. Priya Menon' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit F100' });
    await within(dialog).findByRole('option', { name: /CSE · Computer Science/ });
    expect(within(dialog).getByLabelText('Login email')).toHaveValue('priya@college.test');
    expect(within(dialog).getByLabelText('Department')).toHaveValue('1');
    expect(within(dialog).queryByLabelText('Initial password')).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText('Account active')).toBeChecked();
    const email = within(dialog).getByLabelText('Login email');
    await userEvent.clear(email);
    await userEvent.type(email, 'priya.menon@college.test');
    await userEvent.click(within(dialog).getByLabelText('Account active'));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/faculty/2', {
      name: 'Dr. Priya Menon', email: 'priya.menon@college.test', employee_code: 'F100', department_id: 1, designation: null, max_weekly_hours: 18, is_active: false,
    }));
    expect(await screen.findByText('Faculty member updated')).toBeInTheDocument();
  });

  it('Reset password opens its own dialog, validates, and sends only the new password', async () => {
    api.post.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit F100 Dr. Priya Menon' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Reset password…' }));
    const reset = await screen.findByRole('dialog', { name: 'Reset password for Dr. Priya Menon' });
    expect(screen.queryByRole('dialog', { name: 'Edit F100' })).not.toBeInTheDocument();
    await userEvent.click(within(reset).getByRole('button', { name: 'Reset password' }));
    expect(await within(reset).findByText('Enter a password.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.type(within(reset).getByLabelText('New password'), 'Brand#New77');
    await userEvent.click(within(reset).getByRole('button', { name: 'Reset password' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/faculty/2/reset-password', { password: 'Brand#New77' }));
    expect(await screen.findByText('Password reset')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('Faculty screen - delete / deactivate', () => {
  it('deletes an unused faculty member after a confirmation that mentions the login account', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete F100 Dr. Priya Menon' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this faculty member?' });
    expect(dialog).toHaveTextContent('login account and availability settings');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/faculty/2'));
    expect(await screen.findByText('Faculty member deleted')).toBeInTheDocument();
  });

  it('Cancel changes nothing', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete F100 Dr. Priya Menon' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('a faculty member with teaching assignments is deactivated instead - the delete API is never called', async () => {
    api.patch.mockResolvedValue(fac({ is_active: false }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete F001 Dr. Rakesh Sharma' }));
    const dialog = screen.getByRole('dialog', { name: 'This faculty member is in use' });
    expect(dialog).toHaveTextContent('3 teaching assignments');
    expect(dialog).toHaveTextContent('Deactivate them instead');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Deactivate' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/faculty/1', { is_active: false }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(await screen.findByText('Faculty member deactivated')).toBeInTheDocument();
  });

  it('an inactive faculty member with assignments only gets an OK notice', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete F200 Prof. Old Hand' }));
    const dialog = screen.getByRole('dialog', { name: 'This faculty member is in use' });
    expect(dialog).toHaveTextContent('already inactive');
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('shows the server message in an error toast if the action fails', async () => {
    api.delete.mockRejectedValue(new Error('This faculty member has 1 teaching assignment and cannot be deleted.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete F100 Dr. Priya Menon' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not complete the action')).toBeInTheDocument();
    expect(screen.getByText(/cannot be deleted/)).toBeInTheDocument();
  });
});
