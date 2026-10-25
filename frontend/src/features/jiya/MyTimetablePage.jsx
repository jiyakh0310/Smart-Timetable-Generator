// R11 / R12 - the current published timetable for the signed-in teacher or student. Read-only: there are no actions on this screen.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { Button, Card, EmptyState, Loading, Notice, PageHeader, SelectField, WeeklyTimetable } from '../../components/ui';
import ExportButtons from './ExportButtons.jsx';
import { buildPublishedGrid, publishedApi } from './published.js';

const COPY = {
  faculty: {
    role: 'faculty',
    description: 'Your classes in the timetable the administrator has published. This view is read-only.',
    owner: (v) => `${v.owner.name} · ${v.owner.employee_code}`,
    none: 'You have no classes in this timetable.',
  },
  student: {
    role: 'student',
    description: "Your batch's timetable as published by the administrator. This view is read-only.",
    owner: (v) => `${v.owner.name} · ${v.owner.batch}`,
    none: 'No classes are scheduled for your batch in this timetable.',
  },
};

function MyTimetable({ who }) {
  const copy = COPY[who];
  const [termId, setTermId] = useState(undefined); // undefined = the server's default (the active term)
  const [state, setState] = useState({ loading: true, error: '', view: null });

  const load = useCallback(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true, error: '' }));
    publishedApi[who](termId)
      .then((view) => { if (live) setState({ loading: false, error: '', view }); })
      .catch((err) => { if (live) setState({ loading: false, error: err.message || 'Could not load your timetable.', view: null }); });
    return () => { live = false; };
  }, [who, termId]);

  useEffect(() => load(), [load]);

  const { view } = state;
  const grid = useMemo(() => (view?.timetable ? buildPublishedGrid(view, who) : null), [view, who]);

  let body;
  if (state.loading && !view) {
    body = <Loading label="Loading your timetable…" />;
  } else if (state.error) {
    body = (
      <Card>
        <Notice tone="danger">{state.error}</Notice>
        <Button variant="secondary" onClick={load}>Try again</Button>
      </Card>
    );
  } else if (!view.timetable) {
    body = (
      <Card>
        <EmptyState title="No published timetable yet" icon="calendar">
          {view.term
            ? `No timetable has been published for ${view.term.name} yet. It will appear here once the administrator publishes it.`
            : 'There is no active term at the moment. Your timetable will appear here once one is published.'}
          {view.terms.length > 0 && ' You can choose another term above.'}
        </EmptyState>
      </Card>
    );
  } else {
    body = (
      <Card title={`${view.term.name} · ${view.term.academic_year}`} action={<ExportButtons path={`/${who}/timetable/export`} termId={termId} />} description={`Version ${view.timetable.version}${view.timetable.published_at ? ` · published ${new Date(view.timetable.published_at).toLocaleDateString()}` : ''} · ${copy.owner(view)}`}>
        {view.sessions.length === 0
          ? <EmptyState title={copy.none} icon="calendar" />
          : <WeeklyTimetable days={grid.days} periods={grid.periods} entries={grid.entries} />}
      </Card>
    );
  }

  return (
    <>
      <PageHeader title="My timetable" description={copy.description} breadcrumbs={crumbsFor(copy.role, 'My timetable')} />
      {view && view.terms.length > 1 && (
        <SelectField label="Term" value={view.term?.id ?? ''} onChange={(e) => setTermId(Number(e.target.value))} disabled={state.loading}>
          {!view.terms.some((t) => t.id === view.term?.id) && view.term && <option value={view.term.id}>{view.term.name} (nothing published)</option>}
          {view.terms.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.academic_year}){t.is_active ? ' · current' : ''}</option>)}
        </SelectField>
      )}
      <div aria-live="polite" aria-busy={state.loading}>{body}</div>
    </>
  );
}

export const FacultyTimetablePage = () => <MyTimetable who="faculty" />;
export const StudentTimetablePage = () => <MyTimetable who="student" />;
