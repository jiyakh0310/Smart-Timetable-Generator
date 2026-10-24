import { Navigate, Outlet } from 'react-router-dom';
import { Loading } from '../components/ui';
import { useAuth } from './AuthContext.jsx';
import { ROLE_HOME } from './navConfig.js';

// UI convenience only: hides screens a role should not use.
// The real permission check is always done by the Flask backend.
export default function ProtectedRoute({ role }) {
  const { user, status } = useAuth();
  if (status === 'loading') return <Loading label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={ROLE_HOME[user.role]} replace />;
  return <Outlet />;
}
