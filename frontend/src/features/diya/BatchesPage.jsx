// Diya - R3 Batch management screen (built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import BatchFormDialog from './BatchFormDialog.jsx';
import { BATCHES_PATH, batchesApi, MAX_SEMESTER, usageSentence } from './batches.js';
import { usePrograms } from './useLookup.js';
import useDepartments from './useDepartments.js';

const SEMESTER_OPTIONS = [{ value: '', label: 'All semesters' }, ...Array.from({ length: MAX_SEMESTER }, (_, i) => ({ value: String(i + 1), label: `Semester ${i + 1}` }))];
const INITIAL_FILTERS = { department_id: '', semester_no: '' };

function Enrolment({ batch }) {
  const pct = Math.min(100, Math.round((batch.student_count / batch.strength) * 100));
  return (
    <span className="cell-stack">
      <span><strong>{batch.student_count}</strong> / {batch.strength}</span>
      <span className={`progress${batch.student_count >= batch.strength ? ' is-done' : ''}`} role="img" aria-label={`${batch.student_count} of ${batch.strength} places filled`}><span style={{ width: `${pct}%` }} /></span>
    </span>
  );
}

export default function BatchesPage() {
  const toast = useToast();
  const departments = useDepartments();
  const programs = usePrograms();
  const list = useListQuery(BATCHES_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, batch = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const departmentOptions = [{ value: '', label: 'All departments' }, ...departments.items.map((d) => ({ value: String(d.id), label: d.code }))];

  const columns = [
    { key: 'name', header: 'Batch', cell: (b) => (<span className="cell-stack"><strong>{b.name}</strong><small className="text-muted">{b.program.name}</small></span>) },
    { key: 'department', header: 'Dept', cell: (b) => b.department.code },
    { key: 'semester', header: 'Sem', cell: (b) => b.semester_no },
    { key: 'section', header: 'Section', cell: (b) => b.section },
    { key: 'enrolment', header: 'Students / strength', cell: (b) => <Enrolment batch={b} /> },
    {
      key: 'status',
      header: 'Timetable',
      cell: (b) => (b.scheduled ? <Badge tone="success" dot>Scheduled</Badge> : <Badge>Not scheduled</Badge>),
    },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (b) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(b)} aria-label={`Edit ${b.name}`}><Icon name="edit" size={15} /> Edit</Button>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(b)} aria-label={`Delete ${b.name}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function confirmDelete() {
    setBusy(true);
    try {
      await batchesApi.remove(toDelete.id);
      toast({ tone: 'success', title: 'Batch deleted', message: toDelete.name });
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete the batch', message: err.message });
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
        title="Batches"
        description="Manage the groups of students who attend classes together. Batch strength decides how big a room is needed."
        breadcrumbs={crumbsFor('admin', 'Batches')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add batch</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search batches by name or section" placeholder="Search by name or section" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Department" value={list.filters.department_id} onChange={(v) => list.setFilter('department_id', v)} options={departmentOptions} />
          <FilterSelect label="Semester" value={list.filters.semester_no} onChange={(v) => list.setFilter('semester_no', v)} options={SEMESTER_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Batches"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No batches yet"
          emptyText="Add a batch for each group of students (for example, CSE semester 3 section A). Batches are needed before students can be added."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add batch</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="batches" />
      </Card>

      {formFor !== undefined && <BatchFormDialog batch={formFor} programs={programs.items} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This batch is in use' : 'Delete this batch?'}
        message={
          inUse
            ? `${toDelete.name} is used by ${usageSentence(toDelete.usage)}, so it cannot be deleted. Move or remove those first.`
            : toDelete && `${toDelete.name} will be permanently removed. This cannot be undone.`
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
