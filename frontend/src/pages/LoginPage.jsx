import { Navigate } from 'react-router-dom';
import { useAuth } from '../app/AuthContext.jsx';
import { ROLE_HOME } from '../app/navConfig.js';
import { DepthAccent } from '../components/DashboardHero.jsx';
import { Icon } from '../components/ui';
import usePageTitle from '../hooks/usePageTitle.js';
import { LoginForm } from '../features/isha/index.js';

const POINTS = [
  'No faculty, batch or room clashes',
  'Rooms matched to batch size and type',
  'Admin-approved, published schedules',
];

export default function LoginPage() {
  const { user, status } = useAuth();
  usePageTitle('Sign in');
  if (status === 'ready' && user) return <Navigate to={ROLE_HOME[user.role]} replace />;

  return (
    <div className="login">
      <section className="login-hero" aria-label="About the system">
        <span className="login-shape s1" aria-hidden="true" />
        <span className="login-shape s2" aria-hidden="true" />
        <span className="brand-mark"><Icon name="calendar" size={22} /></span>
        <h1>Smart Timetable Management</h1>
        <p>Conflict-free timetables and automated classroom allocation for the whole institution.</p>
        <ul>
          {POINTS.map((p) => <li key={p}><Icon name="check" size={18} />{p}</li>)}
        </ul>
        <DepthAccent />
      </section>
      <main className="login-panel" id="main">
        <div className="login-card card">
          <h2>Welcome back</h2>
          <p className="lead">Sign in with your institution email to see your timetable.</p>
          <LoginForm />
          <p className="login-foot">Need access? Please contact your administrator.</p>
        </div>
      </main>
    </div>
  );
}
