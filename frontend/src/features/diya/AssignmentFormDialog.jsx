import { useEffect, useState } from 'react';
import { FormDialog, Notice, SelectField, useToast } from '../../components/ui';
import { assignmentsApi, toAssignmentPayload, validateAssignment, weeklyNeed } from './assignments.js';
import useLookup, { useBatchOptions } from './useLookup.js';

function initialForm(a, terms) {
  if (a) return { term_id: String(a.term.id), batch_id: String(a.batch.id), subject_id: String(a.subject.id), faculty_id: String(a.faculty.id) };
  const active = terms.find((t) => t.is_active);
  return { term_id: active ? String(active.id) : '', batch_id: '', subject_id: '', faculty_id: '' };
}

// Create (assignment = null) or edit (assignment = row). Subjects are limited to the chosen batch's semester.
export default function AssignmentFormDialog({ assignment, terms, onClose, onSaved }) {
  const mode = assignment ? 'edit' : 'create';
  const toast = useToast();
  const batches = useBatchOptions();
  const faculty = useLookup('/faculty?per_page=100&active=true');
  const [form, setForm] = useState(() => initialForm(assignment, terms));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  const batch = batches.items.find((b) => String(b.id) === form.batch_id);
  const semester = batch?.semester_no ?? assignment?.batch.semester_no;
  const subjects = useLookup(semester ? `/subjects?per_page=100&semester_no=${semester}` : '/subjects?per_page=1&semester_no=0', (d) => d.items);
  const subject = subjects.items.find((s) => String(s.id) === form.subject_id) ?? (assignment && String(assignment.subject.id) === form.subject_id ? assignment.subject : null);
  const need = weeklyNeed(subject);
  const frozen = mode === 'edit' && assignment.in_use;

  // A subject chosen for another semester is no longer valid when the batch changes.
  useEffect(() => {
    if (form.subject_id && !subjects.loading && subjects.items.length && !subjects.items.some((s) => String(s.id) === form.subject_id)) {
      setForm((f) => ({ ...f, subject_id: '' }));
    }
  }, [subjects.items, subjects.loading, form.subject_id]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  // Faculty list only has active members; keep the current (possibly inactive) teacher selectable when editing.
  const facultyOptions = [...faculty.items];
  if (assignment && !facultyOptions.some((f) => f.id === assignment.faculty.id)) {
    facultyOptions.push({ id: assignment.faculty.id, employee_code: assignment.faculty.employee_code, name: assignment.faculty.name, is_active: false });
  }

  async function submit() {
    setFormError('');
    const clientErrors = validateAssignment(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toAssignmentPayload(form);
      const saved = mode === 'create' ? await assignmentsApi.create(payload) : await assignmentsApi.update(assignment.id, payload);
      toast({
        tone: 'success',
        title: mode === 'create' ? 'Assignment created' : 'Assignment updated',
        message: `${saved.faculty.name} · ${saved.subject.code} · ${saved.batch.name}`,
      });
      saved.warnings.forEach((w) => toast({ tone: 'info', title: 'Check availability', message: w.message }));
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
      title={mode === 'create' ? 'Add teaching assignment' : 'Edit teaching assignment'}
      description={mode === 'create' ? 'Choose who teaches which subject to which batch.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Create assignment' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {frozen && <Notice tone="warning">A generated timetable uses this assignment, so nothing can be changed until that timetable is removed or regenerated.</Notice>}
      {assignment?.warnings.length > 0 && (
        <Notice tone="info">
          <strong>Availability check</strong>
          <ul className="warning-list">{assignment.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>
        </Notice>
      )}
      <div className="form-grid">
        <SelectField label="Term" value={form.term_id} onChange={set('term_id')} error={errors.term_id} disabled={frozen}>
          <option value="">Choose a term</option>
          {terms.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_active ? '' : ' (inactive)'}</option>)}
        </SelectField>
        <SelectField label="Batch" value={form.batch_id} onChange={(e) => setForm((f) => ({ ...f, batch_id: e.target.value, subject_id: '' }))} error={errors.batch_id}
          disabled={frozen || batches.loading} hint={batches.loading ? 'Loading batches…' : undefined}>
          <option value="">Choose a batch</option>
          {batches.items.map((b) => <option key={b.id} value={b.id}>{b.name} · {b.strength} students</option>)}
        </SelectField>
        <SelectField label="Subject" value={form.subject_id} onChange={set('subject_id')} error={errors.subject_id} disabled={frozen || !semester || subjects.loading}
          hint={!semester ? 'Choose a batch first. Only subjects for its semester are listed.' : subjects.loading ? 'Loading subjects…' : `Showing semester ${semester} subjects.`}>
          <option value="">Choose a subject</option>
          {subjects.items.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.name} ({s.class_type})</option>)}
          {subject && !subjects.items.some((s) => s.id === subject.id) && <option value={subject.id}>{subject.code} · {subject.name}</option>}
        </SelectField>
        <SelectField label="Faculty member" value={form.faculty_id} onChange={set('faculty_id')} error={errors.faculty_id} disabled={frozen || faculty.loading}
          hint={faculty.loading ? 'Loading faculty…' : 'Active faculty only.'}>
          <option value="">Choose a faculty member</option>
          {facultyOptions.map((f) => <option key={f.id} value={f.id}>{f.employee_code} · {f.name}{f.is_active ? '' : ' (inactive)'}</option>)}
        </SelectField>
      </div>
      {need && (
        <div className="need-box" role="status">
          <strong>{need.headline}</strong>
          {need.valid ? need.detail : 'This lab subject\'s hours are not a whole number of sessions. Fix the subject first.'}
          <div>Calculated from the subject. It cannot be edited here.</div>
        </div>
      )}
    </FormDialog>
  );
}
