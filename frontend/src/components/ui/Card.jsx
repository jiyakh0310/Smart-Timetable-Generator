import { Link } from 'react-router-dom';
import Icon from './Icon.jsx';

// `flush` removes body padding (use for tables that should touch the card edges).
export function Card({ title, description, action, flush = false, children, className = '', as: Tag = 'section' }) {
  return (
    <Tag className={`card${flush ? ' card-flush' : ''} ${className}`.trim()}>
      {(title || action) && (
        <header className="card-head">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="card-body">{children}</div>
    </Tag>
  );
}

export function StatCard({ label, value, icon, to, hint }) {
  const body = (
    <>
      <div className="stat-top">
        <span>{label}</span>
        {icon && <span className="stat-icon"><Icon name={icon} /></span>}
      </div>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </>
  );
  return to ? <Link className="stat-card" to={to}>{body}</Link> : <div className="stat-card">{body}</div>;
}
