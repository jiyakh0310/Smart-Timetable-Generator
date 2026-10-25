// Isha - R1 Login. Validates on the client for convenience; the backend validates again.
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../app/AuthContext.jsx';
import { ROLE_HOME } from '../../app/navConfig.js';
import { Button, Notice, PasswordField, TextField } from '../../components/ui';

export default function LoginForm() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    const errs = {};
    if (!form.email.trim()) errs.email = 'Enter your email address.';
    if (!form.password) errs.password = 'Enter your password.';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      const user = await login(form.email.trim(), form.password);
      navigate(ROLE_HOME[user.role], { replace: true });
    } catch (err) {
      setFieldErrors(err.details || {});
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="form">
      {error && <Notice tone="danger">{error}</Notice>}
      <TextField label="Email" type="email" autoComplete="username" placeholder="you@institution.edu" value={form.email} onChange={update('email')} error={fieldErrors.email} autoFocus />
      <PasswordField label="Password" autoComplete="current-password" value={form.password} onChange={update('password')} error={fieldErrors.password} />
      <Button type="submit" block loading={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
    </form>
  );
}
