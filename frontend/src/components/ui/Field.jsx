import { useId, useState } from 'react';
import Icon from './Icon.jsx';

// Label + control + hint/error wired together with ids so screen readers announce them.
function FieldShell({ label, hint, error, id, children }) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {children}
      {hint && !error && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}
      {error && (
        <span className="field-error" id={`${id}-error`} role="alert">
          <Icon name="alert" size={14} /> {error}
        </span>
      )}
    </div>
  );
}

const describedBy = (id, hint, error) => (error ? `${id}-error` : hint ? `${id}-hint` : undefined);

export function TextField({ label, hint, error, ...inputProps }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <input id={id} className="input" aria-invalid={error ? 'true' : undefined} aria-describedby={describedBy(id, hint, error)} {...inputProps} />
    </FieldShell>
  );
}

export function TextAreaField({ label, hint, error, ...areaProps }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <textarea id={id} className="input" aria-invalid={error ? 'true' : undefined} aria-describedby={describedBy(id, hint, error)} {...areaProps} />
    </FieldShell>
  );
}

// Password input with a Show / Hide toggle. The toggle is a real button (keyboard and screen-reader friendly) and never changes the value.
export function PasswordField({ label, hint, error, ...inputProps }) {
  const id = useId();
  const [shown, setShown] = useState(false);
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <div className="input-affix">
        <input id={id} className="input" type={shown ? 'text' : 'password'} aria-invalid={error ? 'true' : undefined} aria-describedby={describedBy(id, hint, error)} {...inputProps} />
        <button type="button" aria-pressed={shown} aria-label={shown ? 'Hide password' : 'Show password'} onClick={() => setShown((v) => !v)}>{shown ? 'Hide' : 'Show'}</button>
      </div>
    </FieldShell>
  );
}

export function SelectField({ label, hint, error, children, ...selectProps }) {
  const id = useId();
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <select id={id} className="select" aria-invalid={error ? 'true' : undefined} aria-describedby={describedBy(id, hint, error)} {...selectProps}>
        {children}
      </select>
    </FieldShell>
  );
}

// A single labelled checkbox (e.g. "Active").
export function CheckboxField({ label, hint, ...inputProps }) {
  const id = useId();
  return (
    <div className="field">
      <label className="check" htmlFor={id}>
        <input id={id} type="checkbox" {...inputProps} />
        <span>{label}</span>
      </label>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

// Several checkboxes under one legend. value = array of selected option values.
export function CheckboxGroup({ legend, options, value, onChange, error, hint }) {
  const id = useId();
  const toggle = (optionValue) => onChange(value.includes(optionValue) ? value.filter((v) => v !== optionValue) : [...value, optionValue].sort((a, b) => a - b));
  return (
    <fieldset className="field checkbox-group" aria-describedby={describedBy(id, hint, error)}>
      <legend className="field-label">{legend}</legend>
      <div className="check-row">
        {options.map((o) => (
          <label key={o.value} className="check">
            <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
      {hint && !error && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}
      {error && <span className="field-error" id={`${id}-error`} role="alert"><Icon name="alert" size={14} /> {error}</span>}
    </fieldset>
  );
}
