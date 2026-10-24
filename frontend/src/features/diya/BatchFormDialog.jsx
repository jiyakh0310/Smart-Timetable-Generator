import { useState } from 'react';
import { FormDialog, SelectField, TextField, useToast } from '../../components/ui';
import { batchesApi, MAX_STRENGTH, toBatchPayload, validateBatch } from './batches.js';

function initialForm(batch) {
  if (!batch) return { program_id: '', semester_no: '', section: '', strength: '', name: '' };
  return { program_id: String(batch.program.id), semester_no: String(batch.semester_no), section: batch.section, strength: String(batch.strength), name: batch.name };
}

// Create (batch = null) or edit (batch = row). Mount only while open so each use starts with fresh state.
export default function BatchFormDialog({ batch, programs, onClose, onSaved }) {
  const mode = batch ? 'edit' : 'create';
  const toast = useToast();
  const [form, setForm] = useState(() => initialForm(batch));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const program = programs.find((p) => String(p.id) === form.program_id);
  const enrolled = batch?.student_count ?? 0;
  const lockedScheduling = mode === 'edit' && batch.scheduled;

  async function submit() {
    setFormError('');
    const clientErrors = validateBatch(form, { program, minStrength: enrolled });
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toBatchPayload(form);
      const saved = mode === 'create' ? await batchesApi.create(payload) : await batchesApi.update(batch.id, payload);
      toast({ tone: 'success', title: mode === 'create' ? 'Batch created' : 'Batch updated', message: saved.name });
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
      title={mode === 'create' ? 'Add batch' : `Edit ${batch.name}`}
      description={mode === 'create' ? 'A batch is a group of students who attend classes together.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Create batch' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {lockedScheduling && (
        <p className="field-hint">
          This batch already has teaching assignments or timetable entries, so its program and semester are locked. Name, section and strength can still be changed.
        </p>
      )}
      <div className="form-grid">
        <SelectField label="Program" value={form.program_id} onChange={set('program_id')} error={errors.program_id} disabled={lockedScheduling}>
          <option value="">Choose a program</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.department.code}</option>)}
        </SelectField>
        <TextField label="Semester" type="number" min="1" max={program?.duration_semesters ?? 12} inputMode="numeric" value={form.semester_no} onChange={set('semester_no')}
          error={errors.semester_no} disabled={lockedScheduling} hint={program ? `1 to ${program.duration_semesters}` : undefined} />
        <TextField label="Section" value={form.section} onChange={set('section')} error={errors.section} maxLength={10} placeholder="A" hint="Saved in capitals." />
        <TextField label="Batch strength" type="number" min={Math.max(enrolled, 1)} max={MAX_STRENGTH} inputMode="numeric" value={form.strength} onChange={set('strength')} error={errors.strength}
          hint={enrolled ? `At least ${enrolled} (students already added). Used to choose a big enough room.` : 'Planned number of students. Used to choose a big enough room.'} />
      </div>
      <TextField label="Batch name (optional)" value={form.name} onChange={set('name')} error={errors.name} maxLength={80}
        placeholder="Generated, e.g. CSE Sem 4 - A" hint="Leave blank to generate the name from the department, semester and section." />
    </FormDialog>
  );
}
