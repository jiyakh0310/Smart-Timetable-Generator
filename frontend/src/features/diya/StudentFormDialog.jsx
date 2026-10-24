import { useState } from 'react';
import { Notice, FormDialog, SelectField, TextField, useToast } from '../../components/ui';
import { studentsApi, toStudentPayload, validateStudent } from './students.js';
import { useBatchOptions } from './useLookup.js';

function initialForm(student) {
  if (!student) return { enrollment_no: '', name: '', email: '', batch_id: '' };
  return { enrollment_no: student.enrollment_no, name: student.name, email: student.email || '', batch_id: String(student.batch.id) };
}

// Create (student = null) or edit (student = row). Mount only while open: batch seat counts are fetched fresh each time.
export default function StudentFormDialog({ student, onClose, onSaved }) {
  const mode = student ? 'edit' : 'create';
  const toast = useToast();
  const batches = useBatchOptions();
  const [form, setForm] = useState(() => initialForm(student));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function submit() {
    setFormError('');
    const clientErrors = validateStudent(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toStudentPayload(form);
      const saved = mode === 'create' ? await studentsApi.create(payload) : await studentsApi.update(student.id, payload);
      toast({ tone: 'success', title: mode === 'create' ? 'Student added' : 'Student updated', message: `${saved.enrollment_no} · ${saved.name}` });
      onSaved();
    } catch (err) {
      setErrors(err.details || {});
      setFormError(err.message);
      setBusy(false);
    }
  }

  // A full batch cannot take another student - unless it is the student's current batch.
  const optionLabel = (b) => `${b.name} · ${b.seats_left === 0 ? 'full' : `${b.seats_left} place${b.seats_left === 1 ? '' : 's'} left`}`;
  const isFull = (b) => b.seats_left === 0 && String(b.id) !== (student ? String(student.batch.id) : '');

  return (
    <FormDialog
      open
      wide
      title={mode === 'create' ? 'Add student' : `Edit ${student.enrollment_no}`}
      description={mode === 'create' ? 'Add a student and assign them to a batch.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Add student' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {batches.error && <Notice tone="warning">Could not load the batch list: {batches.error}</Notice>}
      <div className="form-grid">
        <TextField label="Enrollment number" value={form.enrollment_no} onChange={set('enrollment_no')} error={errors.enrollment_no} maxLength={30} placeholder="CSE23001" hint="Saved in capitals. Must be unique." />
        <TextField label="Full name" value={form.name} onChange={set('name')} error={errors.name} maxLength={120} />
        <TextField label="Email (optional)" type="email" value={form.email} onChange={set('email')} error={errors.email} maxLength={255} placeholder="name@college.edu" />
        <SelectField label="Batch" value={form.batch_id} onChange={set('batch_id')} error={errors.batch_id} disabled={batches.loading}
          hint={batches.loading ? 'Loading batches…' : 'Full batches cannot take more students. Raise the batch strength first.'}>
          <option value="">Choose a batch</option>
          {batches.items.map((b) => <option key={b.id} value={b.id} disabled={isFull(b)}>{optionLabel(b)}</option>)}
        </SelectField>
      </div>
    </FormDialog>
  );
}
