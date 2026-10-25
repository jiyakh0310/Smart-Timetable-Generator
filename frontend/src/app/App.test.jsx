import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/ui';
import App from './App.jsx';

let auth;
vi.mock('./AuthContext.jsx', () => ({ useAuth: () => auth }));
const get = vi.fn();
vi.mock('../services/api.js', () => ({ api: { get: (...a) => get(...a), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

const admin = { full_name: 'Dr. Anita Verma', email: 'a@x.test', role: 'admin' };
const student = { full_name: 'Aarav Singh', email: 's@x.test', role: 'student', student: null };

const renderAt = (path) => render(<MemoryRouter initialEntries={[path]}><ToastProvider><App /></ToastProvider></MemoryRouter>);

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ items: [], page: 1, per_page: 10, total: 0, pages: 1 });
  auth = { user: admin, status: 'ready', logout: vi.fn(), login: vi.fn() };
});

describe('read-only published timetable screens (R11 / R12)', () => {
  const view = { owner: { name: 'X', employee_code: 'F001', batch: 'B' }, term: null, terms: [], timetable: null, slots: [], sessions: [] };

  it('/faculty/timetable serves the real screen and only calls the faculty endpoint', async () => {
    auth = { ...auth, user: { full_name: 'Dr. Rakesh Sharma', email: 'f@x.test', role: 'faculty', faculty: null } };
    get.mockResolvedValue(view);
    renderAt('/faculty/timetable');
    expect(await screen.findByRole('heading', { level: 1, name: 'My timetable' })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    await screen.findByText('No published timetable yet');
    expect(get.mock.calls.map((c) => c[0])).toEqual(['/faculty/timetable']);
  });

  it('/student/timetable serves the real screen and only calls the student endpoint', async () => {
    auth = { ...auth, user: student };
    get.mockResolvedValue(view);
    renderAt('/student/timetable');
    expect(await screen.findByRole('heading', { level: 1, name: 'My timetable' })).toBeInTheDocument();
    await screen.findByText('No published timetable yet');
    expect(get.mock.calls.map((c) => c[0])).toEqual(['/student/timetable']);
  });

  it('a student cannot open the faculty timetable and a faculty member cannot open the student one', () => {
    auth = { ...auth, user: student };
    renderAt('/faculty/timetable');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Aarav/);
    auth = { ...auth, user: { full_name: 'Dr. Rakesh Sharma', email: 'f@x.test', role: 'faculty', faculty: null } };
    renderAt('/student/timetable');
    expect(get).not.toHaveBeenCalled();
  });
});

describe('routing of built vs unbuilt screens', () => {
  it('/admin/time-slots serves the real Time Slots screen', async () => {
    renderAt('/admin/time-slots');
    expect(await screen.findByRole('heading', { level: 1, name: 'Time slots' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Add time slots/ }).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/time-slots?'));
  });

  it('/admin/subjects serves the real Subjects screen', async () => {
    renderAt('/admin/subjects');
    expect(await screen.findByRole('heading', { level: 1, name: 'Subjects' })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/subjects?'));
    expect(get).toHaveBeenCalledWith('/departments');
  });

  it.each([['/admin/batches', 'Batches', '/batches?'], ['/admin/students', 'Students', '/students?']])('%s serves the real %s screen', async (path, title, apiPath) => {
    renderAt(path);
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining(apiPath));
  });

  it('/admin/timetables serves the real Timetables screen', async () => {
    renderAt('/admin/timetables');
    expect(await screen.findByRole('heading', { level: 1, name: 'Timetables' })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/timetables?'));
  });

  it('/admin/rooms serves the real Rooms & labs screen', async () => {
    renderAt('/admin/rooms');
    expect(await screen.findByRole('heading', { level: 1, name: 'Rooms & labs' })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/rooms?'));
  });

  it('/admin/assignments serves the real Teaching assignments screen', async () => {
    renderAt('/admin/assignments');
    expect(await screen.findByRole('heading', { level: 1, name: 'Teaching assignments' })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('/teaching-assignments?'));
  });

  it.each([['/admin/faculty', 'Faculty', '/faculty?'], ['/admin/availability', 'Faculty availability', '/faculty?']])('%s serves the real %s screen', async (path, title, apiPath) => {
    renderAt(path);
    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.queryByText('Not available yet')).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining(apiPath));
  });

  it('the old combined "Students & Batches" item is now two built screens', () => {
    renderAt('/admin');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).queryByRole('link', { name: /Students & Batches/ })).not.toBeInTheDocument();
    ['Batches', 'Students', 'Subjects', 'Teaching Assignments', 'Time Slots', 'Faculty Availability'].forEach((label) => expect(within(nav).getByRole('link', { name: new RegExp(label) })).not.toHaveTextContent('Soon'));
    expect(within(nav).getByRole('link', { name: /^Faculty$/ })).not.toHaveTextContent('Soon');
  });

  it('built screens no longer say "Soon", but unbuilt neighbours still do', () => {
    renderAt('/admin/time-slots');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: /Time Slots/ })).not.toHaveTextContent('Soon');
    expect(within(nav).getByRole('link', { name: /Subjects/ })).not.toHaveTextContent('Soon');
    expect(within(nav).getByRole('link', { name: /Rooms/ })).not.toHaveTextContent('Soon');
    expect(within(nav).getByRole('link', { name: /Timetables/ })).not.toHaveTextContent('Soon');
    expect(within(nav).getByRole('link', { name: /Announcements/ })).toHaveTextContent('Soon');
  });

  it('unbuilt admin screens still show the honest "not available yet" page', () => {
    renderAt('/admin/announcements');
    expect(screen.getByRole('heading', { level: 1, name: 'Announcements' })).toBeInTheDocument();
    expect(screen.getByText('Not available yet')).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it.each(['/admin/time-slots', '/admin/students', '/admin/batches', '/admin/faculty', '/admin/availability', '/admin/assignments', '/admin/rooms', '/admin/timetables'])('a student cannot open %s (redirected to their own portal, no data requested)', (path) => {
    auth = { ...auth, user: student };
    renderAt(path);
    expect(screen.queryByRole('heading', { name: /Time slots|Students|Batches|^Faculty|Teaching assignments|Rooms|Timetables/ })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Aarav/);
    expect(get).not.toHaveBeenCalled();
  });

  it.each(['/admin/faculty', '/admin/availability', '/admin/students', '/admin/assignments', '/admin/rooms', '/admin/timetables'])('a faculty member cannot open %s (redirected to the faculty portal, no data requested)', (path) => {
    auth = { ...auth, user: { full_name: 'Dr. Rakesh Sharma', email: 'f@x.test', role: 'faculty', faculty: null } };
    renderAt(path);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Dr\. Rakesh/);
    expect(screen.queryByRole('heading', { name: /^Faculty/ })).not.toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});
