import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NAV } from '../app/navConfig.js';
import { ToastProvider } from '../components/ui';
import AdminDashboard from './admin/AdminDashboard.jsx';
import FacultyDashboard from './faculty/FacultyDashboard.jsx';
import PlannedModulePage from './PlannedModulePage.jsx';
import ProfilePage from './ProfilePage.jsx';
import StudentDashboard from './student/StudentDashboard.jsx';

let user;
vi.mock('../app/AuthContext.jsx', () => ({ useAuth: () => ({ user }) }));
const get = vi.fn();
vi.mock('../services/api.js', () => ({ api: { get: (...a) => get(...a), post: vi.fn() } }));

const admin = { full_name: 'Dr. Anita Verma', email: 'admin@x.test', role: 'admin' };
const faculty = { full_name: 'Dr. Rakesh Sharma', email: 'f@x.test', role: 'faculty', faculty: { employee_code: 'F001', department: 'Computer Science', designation: 'Professor', max_weekly_hours: 18 } };
const student = { full_name: 'Aarav Singh', email: 's@x.test', role: 'student', student: { enrollment_no: 'CSE23001', batch: 'CSE Sem 3 - A', batch_strength: 58, semester_no: 3, program: 'B.Tech CSE', department: 'CSE' } };

// Distinctive numbers prove the page shows API data, not hard-coded figures.
const SUMMARY = {
  counts: { faculty: 13, students: 29, batches: 5, subjects: 17, rooms: 0, time_slots: 41, teaching_assignments: 0 },
  timetables: { total: 3, by_status: { draft: 2, validated: 0, pending_approval: 0, approved: 0, published: 1, rejected: 0, archived: 0 } },
};

const renderPage = (ui) => render(<MemoryRouter><ToastProvider>{ui}</ToastProvider></MemoryRouter>);
let errorSpy;
beforeEach(() => { get.mockReset(); errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {}); });
afterEach(() => { errorSpy.mockRestore(); });
const noConsoleErrors = () => expect(errorSpy).not.toHaveBeenCalled();

describe('Admin dashboard', () => {
  it('shows real counts from the API, setup readiness and the status pipeline', async () => {
    user = admin;
    get.mockResolvedValue(SUMMARY);
    renderPage(<AdminDashboard />);
    expect(await screen.findAllByText('13')).toHaveLength(2); // faculty count from API: stat card + setup table
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const setup = screen.getByRole('table', { name: /setup steps/i });
    const rooms = within(setup).getByRole('row', { name: /Rooms and labs configured/ });
    expect(within(rooms).getByText('Missing')).toBeInTheDocument(); // rooms = 0
    expect(screen.getByText('4 of 6 ready')).toBeInTheDocument();
    expect(screen.getByText('Published')).toBeInTheDocument();
    expect(screen.getByText('3 timetable version(s)')).toBeInTheDocument();
    noConsoleErrors();
  });

  it('links every setup step to its real management screen', async () => {
    user = admin;
    get.mockResolvedValue(SUMMARY);
    renderPage(<AdminDashboard />);
    await screen.findAllByText('13');
    const rooms = screen.getByRole('row', { name: /Rooms and labs configured/ });
    expect(within(rooms).getByRole('link', { name: 'Manage' })).toHaveAttribute('href', '/admin/rooms');
    expect(screen.queryByText(/Planned ·/)).not.toBeInTheDocument(); // nothing left that is not built
    const built = screen.getByRole('row', { name: /Faculty added/ });
    expect(within(built).getByRole('link', { name: 'Manage' })).toHaveAttribute('href', '/admin/faculty');
    const assignments = screen.getByRole('row', { name: /Teaching assignments set/ });
    expect(within(assignments).getByRole('link', { name: 'Manage' })).toHaveAttribute('href', '/admin/assignments');
  });

  it('shows a clear error if the API fails', async () => {
    user = admin;
    get.mockRejectedValue(new Error('Cannot reach the server. Is the backend running?'));
    renderPage(<AdminDashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server');
  });

  it('says no timetable exists when none do (no invented status counts)', async () => {
    user = admin;
    get.mockResolvedValue({ ...SUMMARY, timetables: { total: 0, by_status: { draft: 0, validated: 0, pending_approval: 0, approved: 0, published: 0, rejected: 0, archived: 0 } } });
    renderPage(<AdminDashboard />);
    expect(await screen.findByText(/No timetable generated yet/)).toBeInTheDocument();
  });
});

describe('Faculty dashboard', () => {
  it('shows the real faculty profile and marks timetable/availability as not available yet', () => {
    user = faculty;
    renderPage(<FacultyDashboard />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Dr\. Rakesh/);
    expect(screen.getByText('F001')).toBeInTheDocument();
    expect(screen.getByText('18 h')).toBeInTheDocument();
    expect(screen.getAllByText(/Not available yet/).length).toBeGreaterThanOrEqual(2);
    noConsoleErrors();
  });

  it('warns when the account has no faculty record', () => {
    user = { ...faculty, faculty: null };
    renderPage(<FacultyDashboard />);
    expect(screen.getByRole('status')).toHaveTextContent(/not linked to a faculty record/i);
  });
});

describe('Student dashboard', () => {
  it('shows the student batch, is read-only and has no editing controls', () => {
    user = student;
    renderPage(<StudentDashboard />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Aarav/);
    expect(screen.getAllByText('CSE Sem 3 - A').length).toBeGreaterThan(0);
    expect(screen.getByText('CSE23001')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getAllByText(/Not available yet/).length).toBeGreaterThanOrEqual(2);
    noConsoleErrors();
  });
});

describe('Planned module pages', () => {
  it('every unbuilt screen for every role renders owner, requirement and an honest status', () => {
    user = admin;
    Object.entries(NAV).forEach(([role, items]) => {
      items.filter((i) => !i.done).forEach((item) => {
        const { unmount } = renderPage(<PlannedModulePage item={item} role={role} />);
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(item.label);
        expect(screen.getByText('Not available yet')).toBeInTheDocument();
        expect(screen.getByText(item.owner)).toBeInTheDocument();
        expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
        unmount();
      });
    });
    noConsoleErrors();
  });
});

describe('Profile page', () => {
  it('shows account details and the change-password form for a student', async () => {
    user = student;
    renderPage(<ProfilePage />);
    expect(screen.getByRole('heading', { level: 1, name: 'My profile' })).toBeInTheDocument();
    expect(screen.getByText('CSE23001')).toBeInTheDocument();
    expect(screen.getByLabelText('Current password')).toBeInTheDocument();
    await waitFor(() => noConsoleErrors());
  });
});
