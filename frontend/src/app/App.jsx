import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from '../components/AppShell.jsx';
import { AssignmentsPage, BatchesPage, StudentsPage, SubjectsPage, TimeSlotsPage } from '../features/diya/index.js';
import { AvailabilityPage, FacultyPage } from '../features/isha/index.js';
import { RoomsPage } from '../features/pragya/index.js';
import { FacultyTimetablePage, StudentTimetablePage, TimetablesPage } from '../features/jiya/index.js';
import { Loading } from '../components/ui';
import AdminDashboard from '../pages/admin/AdminDashboard.jsx';
import FacultyDashboard from '../pages/faculty/FacultyDashboard.jsx';
import LoginPage from '../pages/LoginPage.jsx';
import NotFound from '../pages/NotFound.jsx';
import PlannedModulePage from '../pages/PlannedModulePage.jsx';
import ProfilePage from '../pages/ProfilePage.jsx';
import StudentDashboard from '../pages/student/StudentDashboard.jsx';
import { useAuth } from './AuthContext.jsx';
import { NAV, ROLE_HOME } from './navConfig.js';
import ProtectedRoute from './ProtectedRoute.jsx';

// Screens that are really built. Any other nav item shows the honest "not available yet" page.
const SCREENS = {
  'admin:time-slots': TimeSlotsPage,
  'admin:subjects': SubjectsPage,
  'admin:batches': BatchesPage,
  'admin:students': StudentsPage,
  'admin:assignments': AssignmentsPage,
  'admin:rooms': RoomsPage,
  'admin:timetables': TimetablesPage,
  'faculty:timetable': FacultyTimetablePage,
  'student:timetable': StudentTimetablePage,
  'admin:faculty': FacultyPage,
  'admin:availability': AvailabilityPage,
};

const DASHBOARDS = { admin: AdminDashboard, faculty: FacultyDashboard, student: StudentDashboard };

function roleRoutes(role) {
  const Dashboard = DASHBOARDS[role];
  return (
    <Route path={ROLE_HOME[role]} element={<ProtectedRoute role={role} />}>
      <Route element={<AppShell role={role} />}>
        <Route index element={<Dashboard />} />
        {NAV[role]
          .filter((item) => item.path !== '')
          .map((item) => {
            const Screen = item.path === 'profile' ? ProfilePage : SCREENS[`${role}:${item.path}`];
            return <Route key={item.path} path={item.path} element={Screen ? <Screen /> : <PlannedModulePage item={item} role={role} />} />;
          })}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Route>
  );
}

function RoleRedirect() {
  const { user, status } = useAuth();
  if (status === 'loading') return <Loading label="Checking your session…" />;
  return <Navigate to={user ? ROLE_HOME[user.role] : '/login'} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RoleRedirect />} />
      {roleRoutes('admin')}
      {roleRoutes('faculty')}
      {roleRoutes('student')}
      <Route path="*" element={<NotFound standalone />} />
    </Routes>
  );
}
