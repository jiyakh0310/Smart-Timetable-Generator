// Jiya - R7: choose a term and generate a new DRAFT version. Shows the real result summary afterwards.
import { useEffect, useState } from 'react';
import { Badge, Button, Dialog, Notice, SelectField } from '../../components/ui';
import { GENERATION_STATUS, plural, REASON_LABEL, timetablesApi } from './timetables.js';
import WorkloadTable from './WorkloadTable.jsx';

export default function GenerateDialog({ onClose, onGenerated, onView }) {
  const [terms, setTerms] = useState(null);
  const [termId, setTermId] = useState('');
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [preview, setPreview] = useState([]); // R14 warnings for the chosen term, shown before generating

  useEffect(() => {
    let live = true;
    timetablesApi.terms()
      .then((data) => {
        if (!live) return;
        const active = data.items.filter((t) => t.is_active);
        setTerms(active);
        if (active.length === 1) setTermId(String(active[0].id));
      })
      .catch((err) => live && setLoadError(err.message || 'Could not load the terms.'));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    setPreview([]);
    if (!termId) return undefined;
    let live = true;
    timetablesApi.workloadPreview(termId)
      .then((data) => live && setPreview(data?.warnings || []))
      .catch(() => {}); // the preview is advice only; generation reports the same warnings itself
    return () => { live = false; };
  }, [termId]);

  async function submit(e) {
    e.preventDefault();
    if (!termId) { setError('Choose the term to generate for.'); return; }
    setBusy(true);
    setError('');
    try {
      const data = await timetablesApi.generate(Number(termId));
      setResult(data);
      onGenerated();
    } catch (err) {
      setError(err.message || 'Could not generate the timetable.');
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    const g = result.generation;
    const meta = GENERATION_STATUS[g.status];
    return (
      <Dialog open title="Draft timetable generated" onClose={onClose} wide>
        <p><Badge tone={meta.tone} dot>{meta.label}</Badge> <strong>{result.name}</strong> was saved as a <strong>draft</strong>. {meta.text}</p>
        <dl className="summary-list">
          <div><dt>Sessions required</dt><dd>{g.required_sessions}</dd></div>
          <div><dt>Scheduled</dt><dd>{g.scheduled_sessions} ({plural(g.scheduled_periods, 'period', 'periods')})</dd></div>
          <div><dt>Unscheduled</dt><dd>{g.unscheduled_sessions}</dd></div>
        </dl>
        {Object.keys(g.unscheduled_reasons).length > 0 && (
          <p className="text-muted">{Object.entries(g.unscheduled_reasons).map(([code, n]) => `${REASON_LABEL[code] || code}: ${n}`).join(' · ')}</p>
        )}
        {g.warnings.map((w) => <Notice key={w} tone="warning">{w}</Notice>)}
        {g.workload?.length > 0 && <WorkloadTable rows={g.workload} />}
        <div className="dialog-actions">
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button onClick={() => onView(result.id)}>View timetable</Button>
        </div>
      </Dialog>
    );
  }

  const noTerm = terms && terms.length === 0;
  return (
    <Dialog open title="Generate timetable" onClose={busy ? () => {} : onClose} initialFocus="first">
      <form onSubmit={submit} noValidate>
        <p>Creates a new <strong>draft</strong> version for every active teaching assignment in the term. Earlier versions are not changed, and nothing is approved or published.</p>
        {loadError && <Notice tone="danger">{loadError}</Notice>}
        {noTerm && <Notice tone="warning">There is no active term. Activate a term before generating.</Notice>}
        <SelectField label="Term" value={termId} onChange={(e) => { setTermId(e.target.value); setError(''); }} error={error && !busy && !termId ? error : undefined} disabled={!terms || busy}>
          <option value="">{terms ? 'Choose a term' : 'Loading terms…'}</option>
          {(terms || []).map((t) => <option key={t.id} value={t.id}>{t.name} ({t.academic_year})</option>)}
        </SelectField>
        {preview.map((w) => <Notice key={w} tone="warning">{w}</Notice>)}
        {error && termId && <Notice tone="danger">{error}</Notice>}
        <div className="dialog-actions">
          <Button variant="secondary" type="button" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" loading={busy} disabled={!terms || noTerm}>Generate draft</Button>
        </div>
      </form>
    </Dialog>
  );
}
