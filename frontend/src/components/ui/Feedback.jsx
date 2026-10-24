import Icon from './Icon.jsx';

const NOTICE_ICON = { info: 'info', success: 'check', warning: 'alert', danger: 'alert' };

// tone: info | success | warning | danger. Danger is announced immediately (role=alert).
export function Notice({ tone = 'danger', children }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon name={NOTICE_ICON[tone]} size={16} />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ title, icon = 'calendar', children, action }) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon name={icon} size={22} /></span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function Skeleton({ height = 20, width = '100%' }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}
