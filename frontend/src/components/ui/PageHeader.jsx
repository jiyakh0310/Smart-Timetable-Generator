import { Link } from 'react-router-dom';
import usePageTitle from '../../hooks/usePageTitle.js';
import Icon from './Icon.jsx';

// items: [{ label, to? }] - the last item is the current page.
export function Breadcrumbs({ items }) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={item.label}>
              {last || !item.to ? <span aria-current={last ? 'page' : undefined}>{item.label}</span> : <Link to={item.to}>{item.label}</Link>}
              {!last && <Icon name="chevron-right" size={14} />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Every page has exactly one <h1>, rendered here. Also keeps the browser tab title in sync.
export default function PageHeader({ title, description, breadcrumbs = [], actions }) {
  usePageTitle(title);
  return (
    <header className="page-header">
      {breadcrumbs.length > 0 && <Breadcrumbs items={breadcrumbs} />}
      <div className="page-header-row">
        <div>
          <h1>{title}</h1>
          {description && <p>{description}</p>}
        </div>
        {actions && <div className="page-actions">{actions}</div>}
      </div>
    </header>
  );
}
