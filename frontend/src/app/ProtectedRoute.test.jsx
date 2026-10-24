import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ProtectedRoute from './ProtectedRoute.jsx';

const auth = { user: null, status: 'ready' };
vi.mock('./AuthContext.jsx', () => ({ useAuth: () => auth }));

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/student" element={<p>student home</p>} />
        <Route path="/admin" element={<ProtectedRoute role="admin" />}>
          <Route index element={<p>admin secret</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  it('sends signed-out visitors to the login page', () => {
    Object.assign(auth, { user: null, status: 'ready' });
    renderAt('/admin');
    expect(screen.getByText('login page')).toBeInTheDocument();
  });

  it('redirects a student away from admin screens', () => {
    Object.assign(auth, { user: { role: 'student' }, status: 'ready' });
    renderAt('/admin');
    expect(screen.getByText('student home')).toBeInTheDocument();
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
  });

  it('lets the matching role through', () => {
    Object.assign(auth, { user: { role: 'admin' }, status: 'ready' });
    renderAt('/admin');
    expect(screen.getByText('admin secret')).toBeInTheDocument();
  });

  it('shows a loading state, not the login page, while the saved session is checked', () => {
    Object.assign(auth, { user: null, status: 'loading' });
    renderAt('/admin');
    expect(screen.getByRole('status')).toHaveTextContent(/checking your session/i);
    expect(screen.queryByText('login page')).not.toBeInTheDocument();
  });
});
