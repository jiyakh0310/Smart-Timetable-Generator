// Jiya - R7: one saved timetable - weekly grid per batch plus every session that could not be scheduled, with its reason.
import { useEffect, useMemo, useRef, useState } from 'react';
import { DataTable } from '../../components/data';
import { Badge, Button, Card, Icon, Loading, Notice, SelectField, StatusBadge, WeeklyTimetable } from '../../components/ui';
import ValidationResult from './ValidationResult.jsx';
import WorkloadTable from './WorkloadTable.jsx';
import { batchesIn, buildGrid, plural, REASON_LABEL, timetablesApi, validationState } from './timetables.js';

export default function TimetableDetail({ id, onBack, onDiscard, onChanged = () => {} }) {
  const [state, setState] = useState({ loading: true, error: '', timetable: null, slots: [] });
  const [batchId, setBatchId] = useState(null);
  const [validation, setValidation] = useState({ running: false, error: '', result: null });
  const resultHeading = useRef(null);

  useEffect(() => {
    let live = true;
    setState({ loading: true, error: '', timetable: null, slots: [] });
    setValidation({ running: false, error: '', result: null });
    Promise.all([timetablesApi.get(id), timetablesApi.slots()])
      .then(([timetable, slots]) => {
        if (!live) return;
        setState({ loading: false, error: '', timetable, slots: slots.items });
        setBatchId(batchesIn(timetable)[0]?.id ?? null);
      })
      .catch((err) => live && setState({ loading: false, error: err.message || 'Could not load the timetable.', timetable: null, slots: [] }));
    return () => { live = false; };
  }, [id]);

  const { timetable, slots } = state;
  const batches = useMemo(() => (timetable ? batchesIn(timetable) : []), [timetable]);
  const grid = useMemo(() => (timetable && batchId ? buildGrid(slots, timetable.entries, batchId) : null), [timetable, slots, batchId]);

  async function runValidation() {
    setValidation({ running: true, error: '', result: null });
    try {
      const result = await timetablesApi.validate(id);
      setValidation({ running: false, error: '', result });
      setState((s) => ({ ...s, timetable: { ...s.timetable, status: result.status, validation_passed: result.validation_passed, validated_at: result.validated_at, can_discard: ['draft', 'validated'].includes(result.status) } }));
      onChanged();
      setTimeout(() => resultHeading.current?.focus(), 0); // announce the outcome to keyboard and screen-reader users
    } catch (err) {
      setValidation({ running: false, error: err.message || 'Validation could not be completed.', result: null });
    }
  }

  const back = <Button variant="secondary" onClick={onBack}><Icon name="chevron-left" size={16} /> All versions</Button>;
  if (state.loading) return <Loading label="Loading timetable…" />;
  if (state.error) return (<><Notice tone="danger">{state.error}</Notice><div>{back}</div></>);

  const columns = [
    { key: 'batch', header: 'Batch', cell: (u) => u.batch.name },
    { key: 'subject', header: 'Subject', cell: (u) => (<span className="cell-stack"><strong className="mono">{u.subject.code}</strong><small className="text-muted">{u.subject.name} · session {u.session_no}</small></span>) },
    { key: 'faculty', header: 'Faculty', cell: (u) => u.faculty.name },
    { key: 'reason', header: 'Why it was not scheduled', cell: (u) => (<span className="cell-stack"><span><Badge tone="warning">{REASON_LABEL[u.reason_code] || u.reason_code}</Badge></span><small>{u.reason_text}</small></span>) },
  ];

  return (
    <>
      <div className="detail-bar">
        {back}
        <h2>{timetable.name}</h2>
        <StatusBadge status={timetable.status} />
        <Badge tone={validationState(timetable).tone}>{validationState(timetable).label}</Badge>
        <Button onClick={runValidation} loading={validation.running}><Icon name="check" size={16} /> Validate</Button>
        {timetable.can_discard && (
          <Button variant="ghost" className="btn-danger-text" onClick={() => onDiscard(timetable)}><Icon name="trash" size={15} /> Discard draft</Button>
        )}
      </div>
      <p className="text-muted">
        Version {timetable.version} · {timetable.term.name} · {plural(timetable.periods, 'period', 'periods')} scheduled · {plural(timetable.unscheduled_sessions, 'session', 'sessions')} unscheduled
      </p>

      <div aria-live="polite">
        {validation.running && <Loading label="Validating the saved timetable…" />}
        {validation.error && <Notice tone="danger">{validation.error}</Notice>}
      </div>
      {validation.result && <ValidationResult ref={resultHeading} result={validation.result} />}
      {!validation.result && !validation.running && !validation.error && !timetable.validated_at && (
        <Notice tone="info">This timetable has not been validated yet. Validation re-checks the saved timetable for conflicts and for any required session that is missing.</Notice>
      )}

      <Card title="Weekly timetable">
        {batches.length > 0 && (
          <SelectField label="Batch" value={batchId ?? ''} onChange={(e) => setBatchId(Number(e.target.value))}>
            {batches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </SelectField>
        )}
        {grid ? <WeeklyTimetable days={grid.days} periods={grid.periods} entries={grid.entries} emptyHint="No classes were scheduled for this batch." /> : <p className="text-muted">Nothing was scheduled in this version.</p>}
      </Card>

      <Card title="Faculty workload" description="Teaching hours in this timetable against each faculty member's weekly maximum." flush>
        <WorkloadTable rows={timetable.workload || []} />
      </Card>

      <Card title={`Unscheduled sessions (${timetable.unscheduled.length})`} flush>
        <DataTable
          caption="Sessions that could not be scheduled"
          columns={columns}
          rows={timetable.unscheduled}
          emptyTitle="Every required session was scheduled"
          emptyText="There is nothing to resolve in this version."
        />
      </Card>
    </>
  );
}
