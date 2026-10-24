import { useState } from 'react';
import { CheckboxField, FormDialog, Notice, SelectField, TextField, useToast } from '../../components/ui';
import { MAX_CAPACITY, roomsApi, toRoomPayload, TYPE_LABEL, validateRoom } from './rooms.js';

function initialForm(room) {
  if (!room) return { code: '', name: '', location: '', capacity: '', room_type: 'classroom', lab_type: '', is_available: true };
  return { code: room.code, name: room.name, location: room.location || '', capacity: String(room.capacity), room_type: room.room_type, lab_type: room.lab_type || '', is_available: room.is_available };
}

// Create (room = null) or edit (room = row). Mount only while open so each use starts with fresh state.
export default function RoomFormDialog({ room, onClose, onSaved }) {
  const mode = room ? 'edit' : 'create';
  const toast = useToast();
  const [form, setForm] = useState(() => initialForm(room));
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const inUse = mode === 'edit' && room.in_use;
  const entries = room?.usage.timetable_entries ?? 0;
  const goingOutOfService = inUse && room.is_available && !form.is_available;

  async function submit() {
    setFormError('');
    const clientErrors = validateRoom(form, { minCapacity: inUse ? room.min_capacity : 0 });
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setBusy(true);
    try {
      const payload = toRoomPayload(form);
      const saved = mode === 'create' ? await roomsApi.create(payload) : await roomsApi.update(room.id, payload);
      toast({ tone: 'success', title: mode === 'create' ? 'Room added' : 'Room updated', message: `${saved.code} · ${saved.name}` });
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
      title={mode === 'create' ? 'Add room or laboratory' : `Edit ${room.code}`}
      description={mode === 'create' ? 'Rooms are chosen by capacity and type when classes are scheduled.' : undefined}
      error={formError}
      busy={busy}
      submitLabel={mode === 'create' ? 'Add room' : 'Save changes'}
      onClose={onClose}
      onSubmit={submit}
    >
      {inUse && (
        <Notice tone="info">
          This room is used by {entries} timetable entr{entries === 1 ? 'y' : 'ies'}. Its type is locked and its capacity cannot go below {room.min_capacity}.
        </Notice>
      )}
      <div className="form-grid">
        <TextField label="Room code" value={form.code} onChange={set('code')} error={errors.code} maxLength={30} placeholder="R101" hint="Saved in capitals. Must be unique." />
        <TextField label="Room name" value={form.name} onChange={set('name')} error={errors.name} maxLength={100} placeholder="Room 101" />
        <SelectField label="Type" value={form.room_type} onChange={set('room_type')} error={errors.room_type} disabled={inUse}>
          {Object.entries(TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </SelectField>
        <TextField label="Seating capacity" type="number" min={inUse ? Math.max(room.min_capacity, 1) : 1} max={MAX_CAPACITY} inputMode="numeric" value={form.capacity}
          onChange={set('capacity')} error={errors.capacity} hint="Must seat the whole batch." />
        {form.room_type === 'lab' && (
          <TextField label="Lab type (optional)" value={form.lab_type} onChange={set('lab_type')} error={errors.lab_type} maxLength={60} placeholder="Computer" hint="For example Computer or Electronics." />
        )}
        <TextField label="Location (optional)" value={form.location} onChange={set('location')} error={errors.location} maxLength={120} placeholder="Main Block, Floor 1" />
      </div>
      <CheckboxField label="In service" checked={form.is_available} onChange={(e) => setForm((f) => ({ ...f, is_available: e.target.checked }))}
        hint="Untick to take the room out of service. It will not be offered for new classes." />
      {goingOutOfService && (
        <Notice tone="warning">
          {entries} timetable entr{entries === 1 ? 'y uses' : 'ies use'} this room. Taking it out of service is allowed, but validation will report those entries until they are moved.
        </Notice>
      )}
    </FormDialog>
  );
}
