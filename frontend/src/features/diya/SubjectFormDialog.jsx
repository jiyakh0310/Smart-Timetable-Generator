import { useState } from 'react';
import { FormDialog, SelectField, TextField, useToast } from '../../components/ui';
import { defaultRoom, LOCKED_FIELDS, MAX, ROOM_LABEL, ROOM_OPTIONS, subjectsApi, toPayload, validateSubject } from './subjects.js';

function initialForm(subject) {
  if (!subject) {
    return { code: '', name: '', department_id: '', semester_no: '', credits: '', weekly_hours: '', class_type: 'theory', lab_block_periods: '2', required_room_type: 'classroom' };
  }
  return {
    code: subject.code, name: subject.name, department_id: String(subject.department.id), semester_no: String(subject.semester_no),
    credits: String(subject.credits), weekly_hours: String(subject.weekly_hours), class_type: subject.class_type,
    lab_block_periods: String(subject.class_type === 'lab' ? subject.lab_block_periods : 2),
    required_room_type: subject.required_room_type || defaultRoom(subject.class_type),
  };
}

// Create (subject = null) or edit (subject = row). Mount only while open so each use starts with fresh state.
export default function SubjectFormDialog({ subject, departments, onClose, onSaved }) {
  const mode = subject ? 'edit' : 'create';
  const toast = useToast();
  const [form, setForm] = useState(() => initialForm(subject));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = mode === 'edit' && subject.in_use;
  const lockedProps = (field) => (locked && LOCKED_FIELDS.includes(field) ? { disabled: true } : {});
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  // Changing the type resets the room to a valid default for that type.
  const setType = (e) => {
    const class_type = e.target.value;
    setForm((f) => ({ ...f, class_type, required_room_type: ROOM_OPTIONS[class_type].includes(f.required_room_type) ? f.required_room_type : defaultRoom(class_type) }));
  };

  async function submit() {
    setFormError('');
    const clientErrors = validateSubject(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toPayload(form);
      if (mode === 'create') {
        await subjectsApi.create(payload);
        toast({ tone: 'success', title: 'Subject created', message: `${payload.code.toUpperCase()} · ${payload.name}` });
      } else {
        await subjectsApi.update(subject.id, payload);
        toast({ tone: 'success', title: 'Subject updated', message: `${payload.code.toUpperCase()} · ${payload.name}` });
      }
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
      title={mode === 'create' ? 'Add subject' : `Edit ${subject.code}`}
      description={mode === 'create' ? 'Add a subject (course) that can be taught to a batch.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Create subject' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {locked && (
        <p className="field-hint">
          This subject is assigned to {subject.usage.teaching_assignments} batch(es), so department, semester, type, hours and lab session length are locked.
          Remove those teaching assignments to change them.
        </p>
      )}
      <div className="form-grid">
        <TextField label="Subject code" value={form.code} onChange={set('code')} error={errors.code} maxLength={20} placeholder="CS301" hint="Saved in capitals, e.g. CS301." />
        <TextField label="Subject name" value={form.name} onChange={set('name')} error={errors.name} maxLength={150} placeholder="Data Structures" />
        <SelectField label="Department" value={form.department_id} onChange={set('department_id')} error={errors.department_id} {...lockedProps('department_id')}>
          <option value="">Choose a department</option>
          {departments.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.name}</option>)}
        </SelectField>
        <TextField label="Semester" type="number" min="1" max={MAX.semester} inputMode="numeric" value={form.semester_no} onChange={set('semester_no')} error={errors.semester_no} {...lockedProps('semester_no')} />
        <TextField label="Credits" type="number" min="0" max={MAX.credits} inputMode="numeric" value={form.credits} onChange={set('credits')} error={errors.credits} />
        <TextField label="Weekly hours" type="number" min="1" max={MAX.weeklyHours} inputMode="numeric" value={form.weekly_hours} onChange={set('weekly_hours')} error={errors.weekly_hours}
          hint={form.class_type === 'lab' ? 'Total lab hours per week.' : 'Number of periods per week.'} {...lockedProps('weekly_hours')} />
        <SelectField label="Type" value={form.class_type} onChange={setType} error={errors.class_type} {...lockedProps('class_type')}>
          <option value="theory">Theory</option>
          <option value="lab">Lab</option>
        </SelectField>
        {form.class_type === 'lab' && (
          <TextField label="Lab session length (periods)" type="number" min="1" max={MAX.labBlock} inputMode="numeric" value={form.lab_block_periods}
            onChange={set('lab_block_periods')} error={errors.lab_block_periods} hint="Consecutive periods per lab session." {...lockedProps('lab_block_periods')} />
        )}
        <SelectField label="Room requirement" value={form.required_room_type} onChange={set('required_room_type')} error={errors.required_room_type}
          hint={form.class_type === 'lab' ? 'Lab subjects always need a laboratory.' : undefined}>
          {ROOM_OPTIONS[form.class_type].map((r) => <option key={r} value={r}>{ROOM_LABEL[r]}</option>)}
        </SelectField>
      </div>
    </FormDialog>
  );
}
