import { useId } from 'react';
import { Button, Icon } from '../ui';

// Container for the search box and filters above a table.
export function TableToolbar({ children, hasActiveFilters, onClear }) {
  return (
    <div className="toolbar" role="search">
      {children}
      {hasActiveFilters && onClear && <Button variant="ghost" size="sm" onClick={onClear}>Clear</Button>}
    </div>
  );
}

export function SearchBox({ label, value, onChange, placeholder }) {
  const id = useId();
  return (
    <div className="toolbar-field toolbar-search">
      <label htmlFor={id} className="sr-only">{label}</label>
      <Icon name="search" size={16} />
      <input id={id} className="input" type="search" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

// options: [{ value, label }]; the first option is normally { value: '', label: 'All ...' }.
export function FilterSelect({ label, value, onChange, options }) {
  const id = useId();
  return (
    <div className="toolbar-field">
      <label htmlFor={id} className="toolbar-label">{label}</label>
      <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
