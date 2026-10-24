import { useId, useState } from 'react';
import { Button, Icon } from '../../components/ui';
import { generatePassword } from './faculty.js';

// Password field with "Show" and "Generate". Generating reveals the value once so the Admin can pass it on securely.
export default function PasswordInput({ label, value, onChange, error, hint }) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <input
        id={id}
        className="input"
        type={shown ? 'text' : 'password'}
        autoComplete="new-password"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
      />
      <div className="password-tools">
        <label className="check check-sm">
          <input type="checkbox" checked={shown} onChange={(e) => setShown(e.target.checked)} />
          <span>Show</span>
        </label>
        <Button variant="secondary" size="sm" onClick={() => { onChange(generatePassword()); setShown(true); }}>Generate secure password</Button>
      </div>
      {hint && !error && <span className="field-hint" id={`${id}-hint`}>{hint}</span>}
      {error && <span className="field-error" id={`${id}-error`} role="alert"><Icon name="alert" size={14} /> {error}</span>}
    </div>
  );
}
