import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppShell from './AppShell.jsx';

const logout = vi.fn();
let user;
vi.mock('../app/AuthContext.jsx', () => ({ useAuth: () => ({ user, logout }) }));

const renderShell = (role) =>
  render(
    <MemoryRouter initialEntries={[`/${role}`]}>
      <Routes>
        <Route path={`/${role}`} element={<AppShell role={role} />}>
          <Route index element={<h1>Home</h1>} />
        </Route>
        <Route path="/login" element={<p>login page</p>} />
      </Routes>
    </MemoryRouter>,
  );

const student = { full_name: 'Aarav Singh', email: 'a@x.test', role: 'student' };

beforeEach(() => { logout.mockReset(); });

describe('AppShell', () => {
  it('student sees only student navigation', () => {
    user = student;
    renderShell('student');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: /My Timetable/ })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: /Faculty|Subjects|Rooms|Time Slots/ })).not.toBeInTheDocument();
  });

  it('admin navigation is grouped by function and marks unbuilt screens', () => {
    user = { full_name: 'Dr. Anita Verma', email: 'a@x.test', role: 'admin' };
    renderShell('admin');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    ['Overview', 'Academics', 'Infrastructure', 'Scheduling', 'Communication', 'Account'].forEach((g) => expect(within(nav).getByText(g)).toBeInTheDocument());
    expect(within(nav).getByRole('link', { name: /Dashboard/ })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /Announcements/ })).toHaveTextContent('Soon'); // not built yet
    expect(within(nav).getByRole('link', { name: /Rooms/ })).not.toHaveTextContent('Soon'); // built
    expect(within(nav).getByRole('link', { name: /^Faculty$/ })).not.toHaveTextContent('Soon'); // built
  });

  it('asks for confirmation before signing out, and Cancel keeps the session', async () => {
    user = student;
    renderShell('student');
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(screen.getByRole('dialog', { name: 'Sign out?' })).toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
  });

  it('confirming sign out logs out and goes to the login page', async () => {
    user = student;
    renderShell('student');
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sign out' }));
    expect(logout).toHaveBeenCalledOnce();
    expect(await screen.findByText('login page')).toBeInTheDocument();
  });

  it('closes the account menu with Escape', async () => {
    user = student;
    renderShell('student');
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    expect(screen.getByRole('link', { name: 'My profile' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('link', { name: 'My profile' })).not.toBeInTheDocument();
  });
});
