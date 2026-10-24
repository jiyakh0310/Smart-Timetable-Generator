import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Icon } from './ui';

export const initials = (name) =>
  name.replace(/\b(dr|prof)\.?\s/gi, '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';

// Disclosure menu: button toggles a panel; Escape or an outside click closes it.
export default function UserMenu({ user, profileHref, onSignOut }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!root.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') { setOpen(false); root.current?.querySelector('button')?.focus(); } };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);

  return (
    <div className="user-menu" ref={root}>
      <button type="button" className="user-trigger" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((v) => !v)}>
        <span className="avatar" aria-hidden="true">{initials(user.full_name)}</span>
        <span className="user-name">{user.full_name}</span>
        <Icon name="chevron-down" size={16} />
        <span className="sr-only">Account menu</span>
      </button>
      {open && (
        <div className="user-panel">
          <div className="user-panel-head">
            <strong>{user.full_name}</strong>
            <span>{user.email}</span>
          </div>
          <Link className="menu-item" to={profileHref} onClick={() => setOpen(false)}><Icon name="user" /> My profile</Link>
          <button type="button" className="menu-item" onClick={() => { setOpen(false); onSignOut(); }}><Icon name="logout" /> Sign out</button>
        </div>
      )}
    </div>
  );
}
