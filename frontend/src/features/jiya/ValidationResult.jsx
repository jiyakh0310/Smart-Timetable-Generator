// Jiya - R10: readable result of validating a saved timetable (hard errors, completeness, advisory warnings).
import { forwardRef } from 'react';
import { DataTable } from '../../components/data';
import { Badge, Card, Notice } from '../../components/ui';
import { plural, REASON_LABEL } from './timetables.js';

const ValidationResult = forwardRef(function ValidationResult({ result }, headingRef) {
  const { counts } = result;
  const verdict = result.validation_passed
    ? <Notice tone="success"><strong>Validation passed.</strong> There are no hard conflicts and every required session is scheduled. The timetable is marked validated; it is not approved or published.</Notice>
    : (
      <Notice tone="danger">
        <strong>Validation failed.</strong>{' '}
        {[
          counts.hard_errors > 0 && `${plural(counts.hard_errors, 'hard error', 'hard errors')} must be fixed`,
          !result.is_complete && `${plural(counts.unscheduled_sessions, 'required session is', 'required sessions are')} not scheduled`,
        ].filter(Boolean).join(' and ')}.
      </Notice>
    );

  const columns = [
    { key: 'batch', header: 'Batch', cell: (u) => u.batch.name },
    { key: 'subject', header: 'Subject', cell: (u) => (<span className="cell-stack"><strong className="mono">{u.subject.code}</strong><small className="text-muted">{u.subject.name}{u.session_no ? ` · session ${u.session_no}` : ''}</small></span>) },
    { key: 'faculty', header: 'Faculty', cell: (u) => u.faculty.name },
    { key: 'reason', header: 'Reason', cell: (u) => (<span className="cell-stack"><span><Badge tone="warning">{REASON_LABEL[u.reason_code] || u.reason_code}</Badge></span><small>{u.reason_text}</small></span>) },
  ];

  return (
    <Card title="Validation result" description={`Checked ${new Date(result.validated_at).toLocaleString()} against the saved timetable.`}>
      <h3 className="sr-only" tabIndex={-1} ref={headingRef}>Validation {result.validation_passed ? 'passed' : 'failed'}</h3>
      {verdict}
      <dl className="summary-list">
        <div><dt>Sessions required</dt><dd>{counts.required_sessions}</dd></div>
        <div><dt>Sessions scheduled</dt><dd>{counts.scheduled_sessions} ({plural(counts.scheduled_periods, 'period', 'periods')})</dd></div>
        <div><dt>Sessions not scheduled</dt><dd>{counts.unscheduled_sessions}</dd></div>
        <div><dt>Hard errors</dt><dd>{counts.hard_errors}</dd></div>
        <div><dt>Warnings</dt><dd>{counts.warnings}</dd></div>
      </dl>

      <section aria-labelledby="val-hard">
        <h3 id="val-hard" className="subhead">Hard errors ({result.hard_errors.length})</h3>
        {result.hard_errors.length === 0
          ? <p className="text-muted">No hard conflicts: no overlaps, every room fits and is in service, and every slot is a valid class period.</p>
          : (
            <ul className="issue-list">
              {result.hard_errors.map((c, i) => (
                <li key={`${c.code}-${i}`}><Badge tone="danger">{c.code.replace(/_/g, ' ')}</Badge> <span>{c.message}</span></li>
              ))}
            </ul>
          )}
      </section>

      <section aria-labelledby="val-warn">
        <h3 id="val-warn" className="subhead">Warnings ({result.warnings.length})</h3>
        {result.warnings.length === 0
          ? <p className="text-muted">No warnings.</p>
          : (
            <>
              <p className="text-muted">Warnings are advice only, such as a faculty preference that could not be honoured. They never make validation fail.</p>
              <ul className="issue-list">
                {result.warnings.map((c, i) => (
                  <li key={`${c.code}-${i}`}><Badge tone="warning">{c.code.replace(/_/g, ' ')}</Badge> <span>{c.message}</span></li>
                ))}
              </ul>
            </>
          )}
      </section>

      <section aria-labelledby="val-missing">
        <h3 id="val-missing" className="subhead">Required sessions not scheduled ({result.unscheduled.length})</h3>
        <DataTable
          caption="Required sessions that are not scheduled"
          columns={columns}
          rows={result.unscheduled}
          rowKey={(u) => `${u.assignment_id}-${u.session_no ?? 'x'}-${u.reason_text}`}
          emptyTitle="Every required session is scheduled"
          emptyText="Nothing is missing from this timetable."
        />
      </section>
    </Card>
  );
});

export default ValidationResult;
