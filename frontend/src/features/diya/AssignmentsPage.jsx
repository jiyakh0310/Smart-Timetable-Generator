// Teaching assignments screen (Admin only; built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import AssignmentFormDialog from './AssignmentFormDialog.jsx';
import { ASSIGNMENTS_PATH, assignmentsApi, needText } from './assignments.js';
import useLookup, { useBatchOptions } from './useLookup.js';

const TYPE_OPTIONS = [{ value: '', label: 'All types' }, { value: 'theory', label: 'Theory' }, { value: 'lab', label: 'Lab' }];
const INITIAL_FILTERS = { batch_id: '', faculty_id: '', class_type: '' };
const describe = (a) => `${a.subject.code} for ${a.batch.name}`;

export default function AssignmentsPage() {
  const toast = useToast();
  const terms = useLookup('/terms');
  const batches = useBatchOptions();
  const faculty = useLookup('/faculty?per_page=100');
  const list = useListQuery(ASSIGNMENTS_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, assignment = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const batchOptions = [{ value: '', label: 'All batches' }, ...batches.items.map((b) => ({ value: String(b.id), label: b.name }))];
  const facultyOptions = [{ value: '', label: 'All faculty' }, ...faculty.items.map((f) => ({ value: String(f.id), label: `${f.employee_code} · ${f.name}` }))];

  const columns = [
    { key: 'batch', header: 'Batch', cell: (a) => (<span className="cell-stack"><strong>{a.batch.name}</strong><small className="text-muted">{a.term.name}</small></span>) },
    {
      key: 'subject',
      header: 'Subject',
      cell: (a) => (
        <span className="cell-stack">
          <span><strong className="mono">{a.subject.code}</strong> {a.subject.name}</span>
          <small><Badge tone={a.subject.class_type === 'lab' ? 'info' : 'primary'}>{a.subject.class_type === 'lab' ? 'Lab' : 'Theory'}</Badge></small>
        </span>
      ),
    },
    {
      key: 'faculty',
      header: 'Faculty',
      cell: (a) => (<span className="cell-stack"><span>{a.faculty.name}</span><small className="text-muted">{a.faculty.employee_code}{a.faculty.is_active ? '' : ' · inactive'}</small></span>),
    },
    { key: 'need', header: 'Weekly need', cell: (a) => needText(a) },
    {
      key: 'flags',
      header: 'Notes',
      cell: (a) => {
        const flags = [];
        if (a.warnings.length) flags.push(<Badge key="w" tone="warning">Availability check</Badge>);
        if (a.cross_department) flags.push(<Badge key="c" tone="info">Cross-department</Badge>);
        if (a.session_mismatch) flags.push(<Badge key="m" tone="danger">Sessions out of date</Badge>);
        if (a.in_use) flags.push(<Badge key="t" tone="success" dot>In a timetable</Badge>);
        return flags.length ? <span className="flag-stack">{flags}</span> : <span className="text-muted">—</span>;
      },
    },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (a) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(a)} aria-label={`Edit ${describe(a)}`}><Icon name="edit" size={15} /> Edit</Button>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(a)} aria-label={`Delete ${describe(a)}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function confirmDelete() {
    setBusy(true);
    try {
      await assignmentsApi.remove(toDelete.id);
      toast({ tone: 'success', title: 'Assignment deleted', message: `${toDelete.faculty.name} no longer teaches ${toDelete.subject.code} to ${toDelete.batch.name}.` });
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete the assignment', message: err.message });
    } finally {
      setBusy(false);
      setToDelete(null);
      list.reload();
    }
  }

  const inUse = toDelete?.in_use;

  return (
    <>
      <PageHeader
        title="Teaching assignments"
        description="Decide which faculty member teaches which subject to which batch. The weekly sessions are calculated from the subject's hours."
        breadcrumbs={crumbsFor('admin', 'Teaching assignments')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add assignment</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search assignments by subject, faculty or batch" placeholder="Search subject, faculty or batch" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Batch" value={list.filters.batch_id} onChange={(v) => list.setFilter('batch_id', v)} options={batchOptions} />
          <FilterSelect label="Faculty" value={list.filters.faculty_id} onChange={(v) => list.setFilter('faculty_id', v)} options={facultyOptions} />
          <FilterSelect label="Type" value={list.filters.class_type} onChange={(v) => list.setFilter('class_type', v)} options={TYPE_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Teaching assignments"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No teaching assignments yet"
          emptyText="Assign a faculty member to each subject of each batch. A timetable cannot be generated without them."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add assignment</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="assignments" />
      </Card>

      {formFor !== undefined && <AssignmentFormDialog assignment={formFor} terms={terms.items} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This assignment is in a timetable' : 'Delete this assignment?'}
        message={
          inUse
            ? `${describe(toDelete)} is part of a generated timetable, so it cannot be deleted. Remove or regenerate the timetable first.`
            : toDelete && `${toDelete.faculty.name} will no longer teach ${toDelete.subject.code} to ${toDelete.batch.name}. The subject, batch and faculty member stay as they are. This cannot be undone.`
        }
        confirmLabel={inUse ? 'OK' : 'Delete'}
        showCancel={!inUse}
        busy={busy}
        onConfirm={inUse ? () => setToDelete(null) : confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
