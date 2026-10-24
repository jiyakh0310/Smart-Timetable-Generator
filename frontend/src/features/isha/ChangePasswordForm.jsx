// Isha - R1: change own password.
import { useState } from 'react';
import { Button, Notice, TextField, useToast } from '../../components/ui';
import { api } from '../../services/api.js';

const EMPTY = { current_password: '', new_password: '', confirm: '' };

export default function ChangePasswordForm() {
  const toast = useToast();
  const [form, setForm] = useState(EMPTY);
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    const errs = {};
    if (!form.current_password) errs.current_password = 'Enter your current password.';
    if (form.new_password.length < 8) errs.new_password = 'Use at least 8 characters.';
    if (form.new_password !== form.confirm) errs.confirm = 'Passwords do not match.';
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      await api.post('/auth/change-password', { current_password: form.current_password, new_password: form.new_password });
      setForm(EMPTY);
      toast({ tone: 'success', title: 'Password updated', message: 'Use your new password next time you sign in.' });
    } catch (err) {
      setFieldErrors(err.details || {});
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="form form-narrow">
      {error && <Notice tone="danger">{error}</Notice>}
      <TextField label="Current password" type="password" autoComplete="current-password" value={form.current_password} onChange={update('current_password')} error={fieldErrors.current_password} />
      <TextField label="New password" type="password" autoComplete="new-password" value={form.new_password} onChange={update('new_password')} error={fieldErrors.new_password} />
      <TextField label="Confirm new password" type="password" autoComplete="new-password" value={form.confirm} onChange={update('confirm')} error={fieldErrors.confirm} />
      <div><Button type="submit" loading={busy}>{busy ? 'Saving…' : 'Update password'}</Button></div>
    </form>
  );
}
