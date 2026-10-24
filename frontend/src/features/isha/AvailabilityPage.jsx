// Isha - R13 Faculty availability and preferences (Admin-managed weekly grid).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { crumbsFor } from '../../app/navConfig.js';
import { Badge, Button, ButtonLink, Card, ConfirmDialog, EmptyState, Icon, Loading, Notice, PageHeader, SelectField, useToast } from '../../components/ui';
import useLookup from '../diya/useLookup.js';
import { availabilityApi, buildGrid, countStatuses, isDirty, isEditable, nextStatus, STATUS_LABEL, statusMapOf, toEntries } from './availability.js';

const LEGEND = [
  { status: 'available', text: 'Default. The faculty member can be scheduled here.' },
  { status: 'unavailable', text: 'Hard rule. They will never be scheduled in this slot.' },
  { status: 'preferred', text: 'Soft wish. Used when possible, never required.' },
];

function Cell({ slot, status, onCycle }) {
  const when = `${slot.day_name} period ${slot.period_no}, ${slot.start_time} to ${slot.end_time}`;
  if (slot.slot_type === 'break') return <td className="avail-static" aria-label={`${when}: break`}>Break</td>;
  if (!slot.is_active) {
    return <td className="avail-static" aria-label={`${when}: this time slot is disabled`}>Disabled{status !== 'available' ? <small>{STATUS_LABEL[status]} kept</small> : null}</td>;
  }
  return (
    <td>
      <button type="button" className={`avail-cell is-${status}`} onClick={onCycle} aria-label={`${when}: ${STATUS_LABEL[status]}. Activate to change.`}>
        {STATUS_LABEL[status]}
      </button>
    </td>
  );
}

export default function AvailabilityPage() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const facultyList = useLookup('/faculty?per_page=100');
  const selectedId = params.get('faculty') || '';

  const [data, setData] = useState(null); // { faculty, slots, summary }
  const [saved, setSaved] = useState({});
  const [local, setLocal] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [pendingId, setPendingId] = useState(null); // faculty chosen while there are unsaved changes

  const slots = data?.slots ?? [];
  const dirty = data ? isDirty(slots, saved, local) : false;
  const grid = useMemo(() => buildGrid(slots), [slots]);
  const counts = countStatuses(slots, local);

  const load = useCallback(async (id) => {
    setLoading(true);
    setError('');
    setSaveError('');
    try {
      const result = await availabilityApi.get(id);
      setData(result);
      const map = statusMapOf(result.slots);
      setSaved(map);
      setLocal(map);
    } catch (err) {
      setData(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) load(selectedId);
    else setData(null);
  }, [selectedId, load]);

  function chooseFaculty(id) {
    if (dirty) setPendingId(id);
    else setParams(id ? { faculty: id } : {});
  }

  const cycle = (slotId) => setLocal((m) => ({ ...m, [slotId]: nextStatus(m[slotId]) }));
  const clearAll = () => setLocal((m) => {
    const next = { ...m };
    slots.filter(isEditable).forEach((s) => { next[s.time_slot_id] = 'available'; });
    return next;
  });

  async function save() {
    setSaving(true);
    setSaveError('');
    try {
      const result = await availabilityApi.save(data.faculty.id, toEntries(slots, local));
      setData(result);
      const map = statusMapOf(result.slots);
      setSaved(map);
      setLocal(map);
      toast({ tone: 'success', title: 'Availability saved', message: `${result.summary.unavailable} unavailable, ${result.summary.preferred} preferred for ${result.faculty.name}.` });
    } catch (err) {
      const first = err.details && Object.values(err.details)[0];
      setSaveError(first ? `${err.message} ${first}` : err.message);
    } finally {
      setSaving(false);
    }
  }

  const facultyOptions = facultyList.items;
  const noSlots = data && slots.every((s) => !isEditable(s));

  return (
    <>
      <PageHeader
        title="Faculty availability"
        description="Mark the time slots a faculty member cannot teach (a hard rule) or would prefer (a soft wish). Administrators manage this for now."
        breadcrumbs={crumbsFor('admin', 'Faculty availability')}
      />

      <Card>
        <div className="avail-picker">
          <SelectField label="Faculty member" value={selectedId} onChange={(e) => chooseFaculty(e.target.value)} disabled={facultyList.loading} error={facultyList.error || undefined}>
            <option value="">Choose a faculty member</option>
            {facultyOptions.map((f) => <option key={f.id} value={f.id}>{f.employee_code} · {f.name}{f.is_active ? '' : ' (inactive)'}</option>)}
          </SelectField>
        </div>
        <ul className="avail-legend" aria-label="What each status means">
          {LEGEND.map((l) => (
            <li key={l.status}><span className={`avail-swatch is-${l.status}`} aria-hidden="true" /><strong>{STATUS_LABEL[l.status]}</strong> <span className="text-muted">{l.text}</span></li>
          ))}
        </ul>
      </Card>

      {!selectedId && !facultyList.loading && !facultyList.error && facultyOptions.length === 0 && (
        <Card><EmptyState title="No faculty members yet" icon="users" action={<ButtonLink to="/admin/faculty" variant="primary">Go to Faculty</ButtonLink>}>Add faculty first, then set their availability here.</EmptyState></Card>
      )}
      {!selectedId && facultyOptions.length > 0 && (
        <Card><EmptyState title="Choose a faculty member" icon="clock">Pick someone above to see and edit their weekly availability.</EmptyState></Card>
      )}

      {selectedId && loading && <Loading label="Loading availability…" />}
      {selectedId && error && (
        <Card><Notice tone="danger">{error}</Notice><Button variant="secondary" onClick={() => load(selectedId)}>Try again</Button></Card>
      )}

      {selectedId && data && !loading && (
        <Card
          title={`${data.faculty.name} · ${data.faculty.employee_code}`}
          description={data.faculty.is_active ? undefined : 'This faculty member is inactive. Availability can still be edited.'}
          action={
            <span className="badge-row">
              <Badge tone="danger">{counts.unavailable} unavailable</Badge>
              <Badge tone="primary">{counts.preferred} preferred</Badge>
              {dirty && <Badge tone="warning" dot>Unsaved changes</Badge>}
            </span>
          }
        >
          {saveError && <Notice tone="danger">{saveError}</Notice>}
          {noSlots ? (
            <EmptyState title="No usable time slots" icon="clock" action={<ButtonLink to="/admin/time-slots" variant="primary">Go to Time Slots</ButtonLink>}>
              Define active class periods first. Breaks and disabled slots cannot be configured.
            </EmptyState>
          ) : (
            <>
              <div className="table-wrap">
                <table className="avail-grid">
                  <caption className="sr-only">Weekly availability for {data.faculty.name}. Each cell cycles between available, unavailable and preferred.</caption>
                  <thead>
                    <tr>
                      <th scope="col">Period</th>
                      {grid.days.map((d) => <th key={d.day_of_week} scope="col">{d.day_name}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {grid.periods.map((p) => (
                      <tr key={p.period_no}>
                        <th scope="row">Period {p.period_no}<small>{p.start_time}–{p.end_time}</small></th>
                        {grid.days.map((d) => {
                          const slot = grid.cell(d.day_of_week, p.period_no);
                          return slot
                            ? <Cell key={d.day_of_week} slot={slot} status={local[slot.time_slot_id]} onCycle={() => cycle(slot.time_slot_id)} />
                            : <td key={d.day_of_week} className="avail-static" aria-label="No time slot">—</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="avail-actions">
                <Button onClick={save} loading={saving} disabled={!dirty}><Icon name="check" size={16} /> Save availability</Button>
                <Button variant="secondary" onClick={() => setLocal(saved)} disabled={!dirty || saving}>Discard changes</Button>
                <Button variant="ghost" onClick={clearAll} disabled={saving || (counts.unavailable === 0 && counts.preferred === 0)}>Set everything to available</Button>
              </div>
            </>
          )}
        </Card>
      )}

      <ConfirmDialog
        open={pendingId !== null}
        title="Discard unsaved changes?"
        message="You have unsaved availability changes. Switching to another faculty member will discard them."
        confirmLabel="Discard and switch"
        tone="danger"
        onConfirm={() => { const id = pendingId; setPendingId(null); setParams(id ? { faculty: id } : {}); }}
        onCancel={() => setPendingId(null)}
      />
    </>
  );
}
