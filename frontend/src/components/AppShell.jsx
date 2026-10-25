import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, matchPath, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../app/AuthContext.jsx';
import { groupNav, hrefFor, NAV, ROLE_LABEL } from '../app/navConfig.js';
import useMediaQuery from '../hooks/useMediaQuery.js';
import { ConfirmDialog, Icon } from './ui';
import UserMenu from './UserMenu.jsx';

const DESKTOP = '(min-width: 1000px)'; // keep in step with the 999px breakpoint in layout.css
const FLAT_LIMIT = 6;                    // roles with this many pages or fewer get a single flat row of links
const GROUP_ICON = { Academics: 'cap' };
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');
const FOCUSABLE = 'a[href], button:not([disabled])';

/*
 * Top navigation. One <nav> serves both layouts:
 *   desktop (>= 1000px): a horizontal bar; roles with many pages (Admin) group them into dropdown menus,
 *   phones / tablets:    the same nav is a slide-in drawer opened from a compact header button.
 * The profile page lives in the account menu, not in the bar.
 */
export default function AppShell({ role }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const desktop = useMediaQuery(DESKTOP, true);
  const [drawer, setDrawer] = useState(false);
  const [openGroup, setOpenGroup] = useState(null);
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const navRef = useRef(null);
  const menuBtn = useRef(null);
  const closeBtn = useRef(null);

  const profile = NAV[role].find((i) => i.path === 'profile');
  const items = NAV[role].filter((i) => i.path !== 'profile');
  const flat = items.length <= FLAT_LIMIT;
  const groups = groupNav(items);
  const isActive = (item) => Boolean(matchPath({ path: hrefFor(role, item), end: item.path === '' }, pathname));

  // Close menus after navigating, and when the layout changes.
  useEffect(() => { setDrawer(false); setOpenGroup(null); }, [pathname]);
  useEffect(() => { if (desktop) setDrawer(false); else setOpenGroup(null); }, [desktop]);
  useEffect(() => {
    document.body.classList.toggle('has-drawer', drawer && !desktop);
    return () => document.body.classList.remove('has-drawer');
  }, [drawer, desktop]);
  useEffect(() => { if (drawer && !desktop) closeBtn.current?.focus(); }, [drawer, desktop]);

  // Escape closes whichever menu is open and returns focus to its button; the drawer keeps Tab inside; a click elsewhere closes a dropdown.
  useEffect(() => {
    if (!drawer && !openGroup) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        if (drawer) { setDrawer(false); menuBtn.current?.focus(); } else {
          const g = openGroup;
          setOpenGroup(null);
          navRef.current?.querySelector(`[data-group="${g}"]`)?.focus();
        }
      } else if (e.key === 'Tab' && drawer && !desktop) {
        const list = [...navRef.current.querySelectorAll(FOCUSABLE)];
        if (!list.length) return;
        const first = list[0];
        const last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    const onDown = (e) => { if (openGroup && !e.target.closest?.('.nav-dropdown')) setOpenGroup(null); };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDown); };
  }, [drawer, openGroup, desktop]);

  const cancelSignOut = useCallback(() => setConfirmSignOut(false), []);
  function signOut() {
    setConfirmSignOut(false);
    logout();
    navigate('/login', { replace: true });
  }

  const link = (item) => (
    <NavLink to={hrefFor(role, item)} end={item.path === ''} className={({ isActive: on }) => `nav-link${on ? ' active' : ''}`}>
      <Icon name={item.icon} size={17} />
      <span>{item.label}</span>
      {!item.done && <span className="nav-soon">Soon</span>}
    </NavLink>
  );

  const entries = [];
  groups.forEach(({ group, items: members }) => {
    if (flat || (desktop && members.length === 1)) {
      members.forEach((item) => entries.push(<li className="nav-item" key={item.path || 'home'}>{link(item)}</li>));
    } else if (desktop) {
      const open = openGroup === group;
      const id = `menu-${slug(group)}`;
      entries.push(
        <li className="nav-item nav-dropdown" key={group}>
          <button
            type="button"
            className={`nav-link${members.some(isActive) ? ' active' : ''}${open ? ' is-open' : ''}`}
            data-group={group}
            aria-expanded={open}
            aria-haspopup="true"
            aria-controls={id}
            onClick={() => setOpenGroup(open ? null : group)}
          >
            <Icon name={GROUP_ICON[group] || members[0].icon} size={17} />
            <span>{group}</span>
            <span className="nav-caret" aria-hidden="true"><Icon name="chevron-down" size={14} /></span>
          </button>
          <ul id={id} className={`dropdown-panel${open ? ' is-open' : ''}`} aria-label={group}>
            {members.map((item) => <li key={item.path}>{link(item)}</li>)}
          </ul>
        </li>,
      );
    } else {
      entries.push(<li className="nav-group-label" key={`label-${group}`} role="presentation">{group}</li>);
      members.forEach((item) => entries.push(<li className="nav-item" key={item.path || 'home'}>{link(item)}</li>));
    }
  });

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="topnav">
        <div className="topnav-inner">
          <Link className="brand" to={hrefFor(role, items[0])} aria-label="Smart Timetable home">
            <span className="brand-mark"><Icon name="calendar" size={18} /></span>
            <div>
              <strong>Smart Timetable</strong>
              <small>Classroom allocation</small>
            </div>
          </Link>

          <nav id="primary-nav" className={`nav${drawer ? ' open' : ''}`} aria-label="Main" ref={navRef}>
            {!desktop && (
              <div className="drawer-head">
                <span>Menu</span>
                <button type="button" className="icon-btn" ref={closeBtn} onClick={() => { setDrawer(false); menuBtn.current?.focus(); }} aria-label="Close navigation menu">
                  <Icon name="x" size={18} />
                </button>
              </div>
            )}
            <ul className="nav-list">{entries}</ul>
            {!desktop && <div className="drawer-foot">{ROLE_LABEL[role]} access</div>}
          </nav>

          <div className="topnav-end">
            <span className="topnav-role">{ROLE_LABEL[role]}</span>
            <UserMenu user={user} profileHref={hrefFor(role, profile)} onSignOut={() => setConfirmSignOut(true)} />
          </div>
          <button type="button" className="icon-btn menu-btn" ref={menuBtn} onClick={() => setDrawer((v) => !v)} aria-label="Open navigation menu" aria-expanded={drawer} aria-controls="primary-nav">
            <Icon name="menu" size={20} />
          </button>
        </div>
      </header>
      {drawer && !desktop && <button type="button" className="scrim" aria-label="Close menu" tabIndex={-1} onClick={() => setDrawer(false)} />}

      <div className="content">
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
