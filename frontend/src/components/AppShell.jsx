import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../app/AuthContext.jsx';
import { groupNav, hrefFor, NAV, ROLE_LABEL } from '../app/navConfig.js';
import { ConfirmDialog, Icon } from './ui';
import UserMenu from './UserMenu.jsx';

export default function AppShell({ role }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const groups = groupNav(NAV[role]);
  const profile = NAV[role].find((i) => i.path === 'profile');

  // Close the mobile drawer on navigation, and on Escape.
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const cancelSignOut = useCallback(() => setConfirmSignOut(false), []);
  function signOut() {
    setConfirmSignOut(false);
    logout();
    navigate('/login', { replace: true });
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>

      <aside className={`sidebar${menuOpen ? ' open' : ''}`} id="sidebar" aria-label="Sidebar">
        <div className="brand">
          <span className="brand-mark"><Icon name="calendar" size={18} /></span>
          <div>
            <strong>Smart Timetable</strong>
            <small>Classroom allocation</small>
          </div>
        </div>
        <nav className="nav" aria-label="Main">
          {groups.map(({ group, items }) => (
            <div key={group}>
              <div className="nav-group-label" id={`grp-${group}`}>{group}</div>
              <ul className="nav-list" aria-labelledby={`grp-${group}`}>
                {items.map((item) => (
                  <li key={item.path}>
                    <NavLink to={hrefFor(role, item)} end={item.path === ''} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                      <Icon name={item.icon} />
                      <span>{item.label}</span>
                      {!item.done && <span className="nav-soon">Soon</span>}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">{ROLE_LABEL[role]} access</div>
      </aside>
      {menuOpen && <button type="button" className="scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <div className="content">
        <header className="topbar">
          <button type="button" className="icon-btn menu-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="Open navigation menu" aria-expanded={menuOpen} aria-controls="sidebar">
            <Icon name="menu" size={20} />
          </button>
          <span className="topbar-spacer" />
          <span className="topbar-role">{ROLE_LABEL[role]}</span>
          <UserMenu user={user} profileHref={hrefFor(role, profile)} onSignOut={() => setConfirmSignOut(true)} />
        </header>
        <main id="main" className="page" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <ConfirmDialog
        open={confirmSignOut}
        title="Sign out?"
        message="You will need to sign in again to continue."
        confirmLabel="Sign out"
        onConfirm={signOut}
        onCancel={cancelSignOut}
      />
    </div>
  );
}
