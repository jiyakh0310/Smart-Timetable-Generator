import { useState } from 'react';
import { CheckboxField, CheckboxGroup, FormDialog, SelectField, TextField, useToast } from '../../components/ui';
import { DAYS, MAX_PERIOD_NO, timeSlotsApi, toPayload, validateTimeSlot } from './timeSlots.js';

const WORKING_WEEK = [0, 1, 2, 3, 4];

function initialForm(slot) {
  if (!slot) {
    return { days: WORKING_WEEK, day_of_week: 0, period_no: '', start_time: '', end_time: '', slot_type: 'class', is_active: true };
  }
  return { days: [slot.day_of_week], day_of_week: slot.day_of_week, period_no: String(slot.period_no), start_time: slot.start_time, end_time: slot.end_time, slot_type: slot.slot_type, is_active: slot.is_active };
}

// Create (slot = null) or edit (slot = row). Mount it only while open so each use starts with fresh state.
export default function TimeSlotFormDialog({ slot, onClose, onSaved }) {
  const mode = slot ? 'edit' : 'create';
  const toast = useToast();
  const [form, setForm] = useState(() => initialForm(slot));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  async function submit() {
    setFormError('');
    const clientErrors = validateTimeSlot(form, mode);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toPayload(form, mode);
      if (mode === 'create') {
        const result = await timeSlotsApi.create(payload);
        const n = result.items.length;
        toast({ tone: 'success', title: n === 1 ? 'Time slot created' : `${n} time slots created`, message: `Period ${payload.period_no}, ${payload.start_time}-${payload.end_time}` });
      } else {
        await timeSlotsApi.update(slot.id, payload);
        toast({ tone: 'success', title: 'Time slot updated' });
      }
      onSaved();
    } catch (err) {
      setErrors(err.details || {});
      setFormError(err.message);
      setBusy(false);
    }
  }

  const lockedByTimetable = mode === 'edit' && slot.usage?.timetable_entries > 0;

  return (
    <FormDialog
      open
      wide
      title={mode === 'create' ? 'Add time slots' : `Edit ${slot.day_name} · Period ${slot.period_no}`}
      description={mode === 'create' ? 'Define one period and apply it to the working days you select.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Create' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {mode === 'create' ? (
        <CheckboxGroup legend="Days" options={DAYS.map((d) => ({ value: d.value, label: d.label }))} value={form.days}
          onChange={(days) => setForm((f) => ({ ...f, days }))} error={errors.days} hint="Pick every day this period applies to." />
      ) : (
        <SelectField label="Day" value={form.day_of_week} disabled={lockedByTimetable} error={errors.day_of_week}
          onChange={(e) => setForm((f) => ({ ...f, day_of_week: Number(e.target.value) }))}>
          {DAYS.map((d) => <option key={d.value} value={d.value}>{d.name}</option>)}
        </SelectField>
      )}
      {lockedByTimetable && (
        <p className="field-hint">Day, period and times are locked because a timetable uses this slot. You can still change its type or disable it.</p>
      )}
      <div className="form-grid">
        <TextField label="Period number" type="number" min="1" max={MAX_PERIOD_NO} inputMode="numeric" value={form.period_no}
          onChange={set('period_no')} error={errors.period_no} disabled={lockedByTimetable} hint="1 is the first period of the day." />
        <SelectField label="Type" value={form.slot_type} onChange={set('slot_type')} error={errors.slot_type}>
          <option value="class">Class period</option>
          <option value="break">Break</option>
        </SelectField>
        <TextField label="Start time" type="time" value={form.start_time} onChange={set('start_time')} error={errors.start_time} disabled={lockedByTimetable} />
        <TextField label="End time" type="time" value={form.end_time} onChange={set('end_time')} error={errors.end_time} disabled={lockedByTimetable} />
      </div>
      <CheckboxField label="Active" checked={form.is_active} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
        hint="Disabled slots are kept but are not used when timetables are generated." />
    </FormDialog>
  );
}
