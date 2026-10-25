// Jiya - R7 Timetables screen (Admin only): versions of generated drafts, generate a new one, open one, discard a draft.
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, Pagination } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, StatusBadge, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import GenerateDialog from './GenerateDialog.jsx';
import TimetableDetail from './TimetableDetail.jsx';
import { plural, TIMETABLES_PATH, timetablesApi, validationState } from './timetables.js';

export default function TimetablesPage() {
  const toast = useToast();
  const list = useListQuery(TIMETABLES_PATH, { perPage: 10 });
  const [generating, setGenerating] = useState(false);
  const [viewing, setViewing] = useState(null);
  const [toDiscard, setToDiscard] = useState(null);
  const [busy, setBusy] = useState(false);

  async function confirmDiscard() {
    setBusy(true);
    try {
      await timetablesApi.discard(toDiscard.id);
      toast({ tone: 'success', title: 'Draft discarded', message: toDiscard.name });
      if (viewing === toDiscard.id) setViewing(null);
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not discard the draft', message: err.message });
    } finally {
      setBusy(false);
      setToDiscard(null);
      list.reload();
    }
  }

  const columns = [
    { key: 'name', header: 'Timetable', cell: (t) => (<span className="cell-stack"><strong>{t.name}</strong><small className="text-muted">{t.term.name} · {t.term.academic_year}</small></span>) },
    { key: 'version', header: 'Version', cell: (t) => <span className="mono">v{t.version}</span> },
    { key: 'status', header: 'Status', cell: (t) => (<span className="cell-stack"><span><StatusBadge status={t.status} /></span>{t.is_current_published && <small><Badge tone="success">Current</Badge></small>}</span>) },
    { key: 'validation', header: 'Validation', cell: (t) => <Badge tone={validationState(t).tone}>{validationState(t).label}</Badge> },
    { key: 'periods', header: 'Scheduled', cell: (t) => plural(t.periods, 'period', 'periods') },
    {
      key: 'unscheduled',
      header: 'Unscheduled',
      cell: (t) => (t.unscheduled_sessions > 0 ? <Badge tone="warning">{plural(t.unscheduled_sessions, 'session', 'sessions')}</Badge> : <Badge tone="success">None</Badge>),
    },
    { key: 'generated', header: 'Generated', cell: (t) => (t.generated_at ? new Date(t.generated_at).toLocaleString() : '—') },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (t) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setViewing(t.id)} aria-label={`View ${t.name}`}><Icon name="calendar" size={15} /> View</Button>
          {t.can_discard && (
            <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDiscard(t)} aria-label={`Discard ${t.name}`}><Icon name="trash" size={15} /> Discard</Button>
          )}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Timetables"
        description="Generate a draft timetable for a term, review what was scheduled and see why any session could not be. Validate a timetable to check it for conflicts and missing sessions. Unpublished timetables are visible to admins only."
        breadcrumbs={crumbsFor('admin', 'Timetables')}
        actions={<Button onClick={() => setGenerating(true)}><Icon name="plus" size={16} /> Generate timetable</Button>}
      />

      {viewing ? (
        <TimetableDetail id={viewing} onBack={() => setViewing(null)} onDiscard={setToDiscard} onChanged={list.reload} />
      ) : (
        <Card flush>
          <DataTable
            caption="Generated timetable versions"
            columns={columns}
            rows={list.items}
            loading={list.loading}
            initialLoad={list.initialLoad}
            error={list.error}
            onRetry={list.reload}
            emptyTitle="No timetables yet"
            emptyText="Generate a draft from the teaching assignments, rooms and time slots you have set up."
            emptyAction={<Button onClick={() => setGenerating(true)}><Icon name="plus" size={16} /> Generate timetable</Button>}
          />
          <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="timetables" />
        </Card>
      )}

      {generating && (
        <GenerateDialog
          onClose={() => setGenerating(false)}
          onGenerated={list.reload}
          onView={(id) => { setGenerating(false); setViewing(id); }}
        />
      )}

      <ConfirmDialog
        open={Boolean(toDiscard)}
        tone="danger"
        title="Discard this draft?"
        message={toDiscard && `${toDiscard.name} and its ${plural(toDiscard.periods, 'scheduled period', 'scheduled periods')} will be permanently removed. This frees the teaching assignments, rooms and time slots it used. Other versions are not affected.`}
        confirmLabel="Discard draft"
        busy={busy}
        onConfirm={confirmDiscard}
        onCancel={() => setToDiscard(null)}
      />
    </>
  );
}
