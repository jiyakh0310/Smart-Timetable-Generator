import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AppShell from './AppShell.jsx';

const logout = vi.fn();
let user;
vi.mock('../app/AuthContext.jsx', () => ({ useAuth: () => ({ user, logout }) }));

const renderShell = (role, path = `/${role}`) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={`/${role}`} element={<AppShell role={role} />}>
          <Route index element={<h1>Home</h1>} />
          <Route path="faculty" element={<h1>Faculty page</h1>} />
          <Route path="rooms" element={<h1>Rooms page</h1>} />
          <Route path="timetable" element={<h1>Timetable page</h1>} />
        </Route>
        <Route path="/login" element={<p>login page</p>} />
      </Routes>
    </MemoryRouter>,
  );

const student = { full_name: 'Aarav Singh', email: 'a@x.test', role: 'student' };
const faculty = { full_name: 'Dr. Rakesh Sharma', email: 'f@x.test', role: 'faculty' };
const admin = { full_name: 'Dr. Anita Verma', email: 'a@x.test', role: 'admin' };

// matchMedia is not part of jsdom: install a controllable one so both layouts can be tested.
const viewport = { desktop: true, listeners: new Set() };
function setViewport(desktop) {
  viewport.desktop = desktop;
  viewport.listeners = new Set();
  window.matchMedia = vi.fn().mockImplementation(() => ({
    get matches() { return viewport.desktop; },
    addEventListener: (_, fn) => viewport.listeners.add(fn),
    removeEventListener: (_, fn) => viewport.listeners.delete(fn),
  }));
}
const resizeTo = (desktop) => act(() => { viewport.desktop = desktop; viewport.listeners.forEach((fn) => fn()); });

beforeEach(() => { logout.mockReset(); });
afterEach(() => { delete window.matchMedia; document.body.className = ''; });

describe('AppShell - structure', () => {
  it('has a top navigation bar and no sidebar', () => {
    user = admin;
    const { container } = renderShell('admin');
    expect(container.querySelector('header.topnav')).toBeInTheDocument();
    expect(container.querySelector('.sidebar')).not.toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('student sees only student navigation', () => {
    user = student;
    renderShell('student');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: /My Timetable/ })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: /Faculty|Subjects|Rooms|Time Slots/ })).not.toBeInTheDocument();
  });

  it('faculty sees their own pages and none of the admin pages', () => {
    user = faculty;
    renderShell('faculty');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    ['Dashboard', 'My Timetable', 'Availability', 'Workload'].forEach((n) => expect(within(nav).getByRole('link', { name: new RegExp(n) })).toBeInTheDocument());
    expect(within(nav).queryByRole('link', { name: /Rooms|Subjects|Students|Batches|Time Slots/ })).not.toBeInTheDocument();
  });

  it('the profile lives in the account menu, not in the bar', async () => {
    user = student;
    renderShell('student');
    expect(within(screen.getByRole('navigation', { name: 'Main' })).queryByRole('link', { name: /profile/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Account menu/ }));
    expect(screen.getByRole('link', { name: 'My profile' })).toHaveAttribute('href', '/student/profile');
  });
});

describe('AppShell - desktop admin menu', () => {
  beforeEach(() => { user = admin; setViewport(true); });

  it('groups the academic pages in a dropdown and keeps single pages as direct links', () => {
    renderShell('admin');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('button', { name: /Academics/ })).toHaveAttribute('aria-expanded', 'false');
    ['Dashboard', 'Rooms & Labs', 'Timetables', 'Announcements'].forEach((n) => expect(within(nav).getByRole('link', { name: new RegExp(n) })).toBeInTheDocument());
    expect(within(nav).getByRole('link', { name: /Dashboard/ })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /Announcements/ })).toHaveTextContent('Soon'); // not built yet
    expect(within(nav).getByRole('link', { name: /Rooms/ })).not.toHaveTextContent('Soon');       // built
    expect(within(nav).getByRole('link', { name: /^Faculty$/ })).not.toHaveTextContent('Soon');
  });

  it('opens the dropdown with a click, lists every academic page, and Escape closes it and restores focus', async () => {
    renderShell('admin');
    const trigger = screen.getByRole('button', { name: /Academics/ });
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const panel = document.getElementById(trigger.getAttribute('aria-controls'));
    expect(panel).toHaveClass('is-open');
    ['Faculty', 'Faculty Availability', 'Batches', 'Students', 'Subjects', 'Teaching Assignments', 'Time Slots'].forEach((n) => expect(within(panel).getByRole('link', { name: new RegExp(`^${n}$`) })).toBeInTheDocument());
    await userEvent.keyboard('{Escape}');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(panel).not.toHaveClass('is-open');
    expect(trigger).toHaveFocus();
  });

  it('a click elsewhere closes the dropdown', async () => {
    renderShell('admin');
    const trigger = screen.getByRole('button', { name: /Academics/ });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole('main'));
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('choosing a page navigates, closes the menu and marks the group active', async () => {
    renderShell('admin');
    const trigger = screen.getByRole('button', { name: /Academics/ });
    await userEvent.click(trigger);
    await userEvent.click(within(document.getElementById(trigger.getAttribute('aria-controls'))).getByRole('link', { name: /^Faculty$/ }));
    expect(await screen.findByRole('heading', { name: 'Faculty page' })).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveClass('active');
  });

  it('is operable by keyboard: Tab reaches the trigger and Enter opens it', async () => {
    renderShell('admin');
    const trigger = screen.getByRole('button', { name: /Academics/ });
    trigger.focus();
    await userEvent.keyboard('{Enter}');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not show the phone menu button content as an open drawer', () => {
    renderShell('admin');
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: 'Close navigation menu' })).not.toBeInTheDocument();
  });
});

describe('AppShell - phone drawer', () => {
  beforeEach(() => { user = admin; setViewport(false); });

  it('shows every page under group headings inside the drawer, with no dropdown buttons', () => {
    renderShell('admin');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    ['Overview', 'Academics', 'Infrastructure', 'Scheduling', 'Communication'].forEach((g) => expect(within(nav).getByText(g)).toBeInTheDocument());
    expect(within(nav).queryByRole('button', { name: /Academics/ })).not.toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: /Time Slots/ })).toBeInTheDocument();
  });

  it('opens from the menu button, moves focus inside, and locks background scrolling', async () => {
    renderShell('admin');
    const open = screen.getByRole('button', { name: 'Open navigation menu' });
    await userEvent.click(open);
    expect(open).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('navigation', { name: 'Main' })).toHaveClass('open');
    expect(screen.getByRole('button', { name: 'Close navigation menu' })).toHaveFocus();
    expect(document.body).toHaveClass('has-drawer');
  });

  it('closes with Escape and returns focus to the menu button', async () => {
    renderShell('admin');
    const open = screen.getByRole('button', { name: 'Open navigation menu' });
    await userEvent.click(open);
    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveClass('open');
    expect(open).toHaveFocus();
    expect(document.body).not.toHaveClass('has-drawer');
  });

  it('closes with the close button and with a tap on the backdrop', async () => {
    renderShell('admin');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    await userEvent.click(screen.getByRole('button', { name: 'Close navigation menu' }));
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveClass('open');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    await userEvent.click(screen.getByRole('button', { name: 'Close menu' }));
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveClass('open');
  });

  it('closes after choosing a page', async () => {
    renderShell('admin');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: /Rooms/ }));
    expect(await screen.findByRole('heading', { name: 'Rooms page' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveClass('open');
  });

  it('keeps Tab inside the open drawer', async () => {
    renderShell('student');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    const links = within(screen.getByRole('navigation', { name: 'Main' })).getAllByRole('link');
    links[links.length - 1].focus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close navigation menu' })).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(links[links.length - 1]).toHaveFocus();
  });

  it('closes the drawer if the window grows to desktop width', async () => {
    renderShell('admin');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }));
    expect(document.body).toHaveClass('has-drawer');
    resizeTo(true);
    expect(document.body).not.toHaveClass('has-drawer');
  });
});

describe('AppShell - signing out', () => {
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
