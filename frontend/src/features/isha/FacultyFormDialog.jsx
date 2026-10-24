import { useState } from 'react';
import { Button, CheckboxField, FormDialog, SelectField, TextField, useToast } from '../../components/ui';
import PasswordInput from './PasswordInput.jsx';
import { facultyApi, MAX_WEEKLY_HOURS, toFacultyPayload, validateFaculty } from './faculty.js';

function initialForm(faculty) {
  if (!faculty) {
    return { name: '', email: '', employee_code: '', department_id: '', designation: '', max_weekly_hours: '18', password: '', is_active: true };
  }
  return {
    name: faculty.name, email: faculty.email, employee_code: faculty.employee_code, department_id: String(faculty.department.id),
    designation: faculty.designation || '', max_weekly_hours: String(faculty.max_weekly_hours), password: '', is_active: faculty.is_active,
  };
}

// Create (faculty = null) or edit (faculty = row). Creating also creates the faculty member's login (role is always "faculty").
export default function FacultyFormDialog({ faculty, departments, onClose, onSaved, onResetPassword }) {
  const mode = faculty ? 'edit' : 'create';
  const toast = useToast();
  const [form, setForm] = useState(() => initialForm(faculty));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function submit() {
    setFormError('');
    const clientErrors = validateFaculty(form, mode);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toFacultyPayload(form, mode);
      const saved = mode === 'create' ? await facultyApi.create(payload) : await facultyApi.update(faculty.id, payload);
      toast({
        tone: 'success',
        title: mode === 'create' ? 'Faculty member added' : 'Faculty member updated',
        message: mode === 'create' ? `${saved.name} can now sign in with the password you set.` : saved.name,
      });
      onSaved();
    } catch (err) {
      setErrors(err.details || {});
      setFormError(err.message);
      setBusy(false);
    }
  }

  return (
    <FormDialog
      open
      wide
      title={mode === 'create' ? 'Add faculty member' : `Edit ${faculty.employee_code}`}
      description={mode === 'create' ? 'This also creates their login account (role: faculty).' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Add faculty member' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      <div className="form-grid">
        <TextField label="Full name" value={form.name} onChange={set('name')} error={errors.name} maxLength={120} placeholder="Dr. Priya Menon" />
        <TextField label="Login email" type="email" value={form.email} onChange={set('email')} error={errors.email} maxLength={255} placeholder="name@college.edu"
          hint={mode === 'edit' ? 'Changing this changes how they sign in.' : undefined} />
        <TextField label="Employee code" value={form.employee_code} onChange={set('employee_code')} error={errors.employee_code} maxLength={30} placeholder="F001" hint="Saved in capitals. Must be unique." />
        <SelectField label="Department" value={form.department_id} onChange={set('department_id')} error={errors.department_id}>
          <option value="">Choose a department</option>
          {departments.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
        </SelectField>
        <TextField label="Designation (optional)" value={form.designation} onChange={set('designation')} error={errors.designation} maxLength={80} placeholder="Assistant Professor" />
        <TextField label="Weekly teaching hour limit" type="number" min="1" max={MAX_WEEKLY_HOURS} inputMode="numeric" value={form.max_weekly_hours}
          onChange={set('max_weekly_hours')} error={errors.max_weekly_hours} hint={`1 to ${MAX_WEEKLY_HOURS} hours.`} />
      </div>

      {mode === 'create' && (
        <PasswordInput label="Initial password" value={form.password} onChange={(password) => setForm((f) => ({ ...f, password }))} error={errors.password}
          hint="8+ characters with a letter and a number. Share it securely; they can change it from their profile." />
      )}

      {mode === 'edit' && (
        <>
          <CheckboxField label="Account active" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            hint="Untick to deactivate: they can no longer sign in, but all their records are kept." />
          <div>
            <Button variant="secondary" size="sm" onClick={() => onResetPassword(faculty)}>Reset password…</Button>
          </div>
        </>
      )}
    </FormDialog>
  );
}
