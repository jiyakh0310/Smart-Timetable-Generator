import { useState } from 'react';
import { FormDialog, useToast } from '../../components/ui';
import PasswordInput from './PasswordInput.jsx';
import { facultyApi, passwordProblem } from './faculty.js';

// Admin sets a new password for a faculty member. The server stores only a hash and never returns it.
export default function ResetPasswordDialog({ faculty, onClose }) {
  const toast = useToast();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    setFormError('');
    const problem = passwordProblem(password, [faculty.email, faculty.employee_code, faculty.name]);
    setError(problem);
    if (problem) return;
    setBusy(true);
    try {
      await facultyApi.resetPassword(faculty.id, password);
      toast({ tone: 'success', title: 'Password reset', message: `Share the new password with ${faculty.name} securely.` });
      onClose();
    } catch (err) {
      setError(err.details?.password || '');
      setFormError(err.message);
      setBusy(false);
    }
  }

  return (
    <FormDialog
      open
      title={`Reset password for ${faculty.name}`}
      description="Their current password stops working. Sessions that are already signed in stay valid until they expire."
      error={formError}
      busy={busy}
      submitLabel="Reset password"
      onClose={onClose}
      onSubmit={submit}
    >
      <PasswordInput label="New password" value={password} onChange={setPassword} error={error} hint="8+ characters with a letter and a number." />
    </FormDialog>
  );
}
