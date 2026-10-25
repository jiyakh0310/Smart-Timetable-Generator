// Jiya - R16: review, approve and publish a timetable. The server re-validates on every step; this panel only asks and reports.
import { useState } from 'react';
import { Badge, Button, Card, ConfirmDialog, Dialog, Notice, StatusBadge, TextAreaField, TIMETABLE_STATUS } from '../../components/ui';
import { timetablesApi } from './timetables.js';

const STEPS = ['draft', 'validated', 'pending_approval', 'approved', 'published'];
// where a rejected / archived timetable sits on the road
const STEP_OF = { rejected: 'draft', archived: 'published' };

const ACTIONS = {
  submit: {
    label: 'Submit for approval',
    title: 'Submit this timetable for approval?',
    message: 'The saved timetable is validated again now. If it has any hard conflict, a faculty overload or a missing session it will be refused. Once submitted it can no longer be edited.',
    confirm: 'Submit',
    success: 'Submitted for approval',
  },
  approve: {
    label: 'Approve',
    title: 'Approve this timetable?',
    message: 'The saved timetable is validated again now. Approving does not publish it. An approved timetable can no longer be edited.',
    confirm: 'Approve',
    success: 'Timetable approved',
  },
  publish: {
    label: 'Publish',
    title: 'Publish this timetable?',
    message: (t) => `It is validated one more time, then becomes the current published version of ${t.term.name}. Any version that is published now is archived, and its history is kept. Published timetables cannot be edited or deleted; to change one, generate a new version.`,
    confirm: 'Publish',
    success: 'Timetable published',
  },
};

export default function ReviewPanel({ timetable, onDone, onFailedValidation, onRefresh }) {
  const [pending, setPending] = useState(null); // action waiting for confirmation
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const allowed = timetable.allowed_actions || [];
  const position = STEPS.indexOf(STEP_OF[timetable.status] || timetable.status);

  async function run(action, body) {
    setBusy(true);
    setError('');
    try {
      const result = await timetablesApi.workflow(timetable.id, action, body);
      setPending(null);
      setRejecting(false);
      setReason('');
      onDone(result, action);
    } catch (err) {
      setPending(null);
      if (err.code === 'validation_failed' && err.details?.validation) onFailedValidation(err.details.validation);
      else if (err.code === 'illegal_transition') onRefresh();
      if (rejecting && err.code === 'validation_error') setReasonError(err.details?.reason || err.message);
      else setError(err.message || 'The action could not be completed.');
    } finally {
      setBusy(false);
    }
  }

  function submitRejection(e) {
    e.preventDefault();
    const clean = reason.trim().replace(/\s+/g, ' ');
    if (clean.length < 5) { setReasonError('Give a reason of at least 5 characters.'); return; }
    if (clean.length > 500) { setReasonError('Use at most 500 characters.'); return; }
    run('reject', { reason: clean });
  }

  const meta = TIMETABLE_STATUS[timetable.status];
  const config = pending ? ACTIONS[pending] : null;

  return (
    <Card title="Review and publish" description="Validate, approve and publish. Each step re-checks the saved timetable on the server.">
      <ol className="steps" aria-label="Timetable workflow">
        {STEPS.map((step, i) => (
          <li key={step} className={i < position ? 'is-done' : i === position ? 'is-current' : ''} aria-current={i === position ? 'step' : undefined}>
            {TIMETABLE_STATUS[step].label}
          </li>
        ))}
      </ol>
      <p>
        <StatusBadge status={timetable.status} />{' '}
        {timetable.is_current_published && <Badge tone="success">Current published version</Badge>}{' '}
        <span className="text-muted">{meta?.help}</span>
      </p>
      {timetable.status === 'rejected' && timetable.rejection_reason && (
        <Notice tone="warning"><strong>Rejected:</strong> {timetable.rejection_reason} Fix the timetable (it can be edited again) and submit it again.</Notice>
      )}
      {timetable.status === 'archived' && <Notice tone="info">A newer version has replaced this one. It is kept as history and cannot be changed.</Notice>}
      {timetable.approved_at && <p className="text-muted">Approved {new Date(timetable.approved_at).toLocaleString()}.</p>}
      {timetable.published_at && <p className="text-muted">Published {new Date(timetable.published_at).toLocaleString()}.</p>}
      {error && <Notice tone="danger">{error}</Notice>}

      {allowed.length > 0 ? (
        <div className="review-actions">
          {allowed.includes('submit') && <Button onClick={() => setPending('submit')}>{ACTIONS.submit.label}</Button>}
          {allowed.includes('approve') && <Button onClick={() => setPending('approve')}>{ACTIONS.approve.label}</Button>}
          {allowed.includes('publish') && <Button variant="success" onClick={() => setPending('publish')}>{ACTIONS.publish.label}</Button>}
          {allowed.includes('reject') && <Button variant="secondary" className="btn-danger-text" onClick={() => { setReasonError(''); setRejecting(true); }}>{timetable.status === 'approved' ? 'Withdraw approval…' : 'Reject…'}</Button>}
        </div>
      ) : (
        <p className="text-muted">No further action is available for a {timetable.status} timetable.</p>
      )}

      <ConfirmDialog
        open={Boolean(pending)}
        tone={pending === 'publish' ? 'success' : 'primary'}
        title={config?.title ?? ''}
        message={config ? (typeof config.message === 'function' ? config.message(timetable) : config.message) : ''}
        confirmLabel={config?.confirm}
        busy={busy}
        onConfirm={() => run(pending)}
        onCancel={() => setPending(null)}
      />

      <Dialog open={rejecting} title={timetable.status === 'approved' ? 'Withdraw this approval?' : 'Reject this timetable?'} onClose={busy ? () => {} : () => setRejecting(false)} initialFocus="first">
        <form onSubmit={submitRejection} noValidate>
          <p>The timetable goes back for changes. You can edit it again and submit it again. The reason is saved with it.</p>
          <TextAreaField label="Reason" value={reason} onChange={(e) => { setReason(e.target.value); setReasonError(''); }} error={reasonError} rows={3} maxLength={500} disabled={busy} />
          <div className="dialog-actions">
            <Button variant="secondary" type="button" onClick={() => setRejecting(false)} disabled={busy}>Cancel</Button>
            <Button variant="danger" type="submit" loading={busy}>Reject timetable</Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}

export { ACTIONS };
