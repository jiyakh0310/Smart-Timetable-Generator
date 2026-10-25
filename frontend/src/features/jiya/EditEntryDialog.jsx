// Jiya - R15: move one session to another day/time and/or room. The lists are a convenience; the server re-checks everything.
import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog, Loading, Notice, SelectField } from '../../components/ui';
import { timetablesApi } from './timetables.js';

const slotLabel = (o) => `${o.day_name} · period ${o.period_no} · ${o.start_time}–${o.end_time}${o.is_current ? ' (current)' : ''}`;
const roomLabel = (r) => `${r.code} · ${r.name} · ${r.capacity} seats${r.is_current ? ' (current)' : ''}`;

export default function EditEntryDialog({ timetableId, entry, onClose, onSaved }) {
  const [state, setState] = useState({ loading: true, error: '', data: null });
  const [slotId, setSlotId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [busy, setBusy] = useState(false);
  const [conflicts, setConflicts] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let live = true;
    timetablesApi.editOptions(timetableId, entry.id)
      .then((data) => {
        if (!live) return;
        setState({ loading: false, error: '', data });
        setSlotId(String(data.current.time_slot_id));
        setRoomId(String(data.current.room_id));
      })
      .catch((err) => live && setState({ loading: false, error: err.message || 'Could not load the choices.', data: null }));
    return () => { live = false; };
  }, [timetableId, entry.id]);

  const { data } = state;
  const chosen = useMemo(() => data?.options.find((o) => String(o.time_slot_id) === slotId), [data, slotId]);
  const rooms = chosen?.rooms ?? [];
  const unchanged = data && slotId === String(data.current.time_slot_id) && roomId === String(data.current.room_id);

  function pickSlot(value) {
    setSlotId(value);
    setConflicts([]);
    setError('');
    const next = data.options.find((o) => String(o.time_slot_id) === value);
    // keep the room when it is still suitable there, otherwise the smallest suitable one
    setRoomId(String(next.rooms.find((r) => String(r.id) === roomId)?.id ?? next.rooms[0].id));
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setConflicts([]);
    setError('');
    try {
      const result = await timetablesApi.editEntry(timetableId, entry.id, { time_slot_id: Number(slotId), room_id: Number(roomId) });
      onSaved(result);
    } catch (err) {
      setConflicts(err.details?.conflicts || []);
      setError(err.message || 'Could not save the change.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open title="Move class" onClose={busy ? () => {} : onClose} initialFocus="first">
      {state.loading && <Loading label="Loading available times and rooms…" />}
      {state.error && <Notice tone="danger">{state.error}</Notice>}
      {data && (
        <form onSubmit={save} noValidate>
          <p>
            <strong>{data.subject.code} · {data.subject.name}</strong> for {data.batch.name}, taught by {data.faculty.name}.
            {data.periods > 1 && ` This is a ${data.periods}-period lab; it moves as one block.`}
          </p>
          {data.options.length <= 1 && <Notice tone="info">No other time or room is currently free for this class without causing a conflict.</Notice>}
          <SelectField label="Day and time" value={slotId} onChange={(e) => pickSlot(e.target.value)} disabled={busy} hint="Only times with no clash, a suitable room and enough weekly hours are listed.">
            {data.options.map((o) => <option key={o.time_slot_id} value={o.time_slot_id}>{slotLabel(o)}</option>)}
          </SelectField>
          <SelectField label="Room" value={roomId} onChange={(e) => { setRoomId(e.target.value); setConflicts([]); setError(''); }} disabled={busy} hint="Rooms that are big enough, of the right type, in service and free at that time.">
            {rooms.map((r) => <option key={r.id} value={r.id}>{roomLabel(r)}</option>)}
          </SelectField>
          <Notice tone="info">After saving, the whole timetable is re-validated and its validation result is updated.</Notice>
          {error && (
            <Notice tone="danger">
              <strong>This change was not saved.</strong> {error}
              {conflicts.length > 1 && (
                <ul className="conflict-list">{conflicts.map((c, i) => <li key={`${c.code}-${i}`}>{c.message}</li>)}</ul>
              )}
            </Notice>
          )}
          <div className="dialog-actions">
            <Button variant="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button type="submit" loading={busy} disabled={unchanged}>Save change</Button>
          </div>
        </form>
      )}
      {!data && !state.loading && (
        <div className="dialog-actions"><Button variant="secondary" onClick={onClose}>Close</Button></div>
      )}
    </Dialog>
  );
}
