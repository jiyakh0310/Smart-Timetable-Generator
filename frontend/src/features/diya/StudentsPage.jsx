// Diya - R3 Student management screen (Admin only; built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import { MAX_SEMESTER } from './batches.js';
import StudentFormDialog from './StudentFormDialog.jsx';
import { STUDENTS_PATH, studentsApi } from './students.js';
import { useBatchOptions } from './useLookup.js';

const SEMESTER_OPTIONS = [{ value: '', label: 'All semesters' }, ...Array.from({ length: MAX_SEMESTER }, (_, i) => ({ value: String(i + 1), label: `Semester ${i + 1}` }))];
const INITIAL_FILTERS = { batch_id: '', semester_no: '' };

export default function StudentsPage() {
  const toast = useToast();
  const batches = useBatchOptions();
  const list = useListQuery(STUDENTS_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, student = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const batchOptions = [{ value: '', label: 'All batches' }, ...batches.items.map((b) => ({ value: String(b.id), label: b.name }))];

  const columns = [
    { key: 'number', header: 'Enrollment no.', cell: (s) => <strong className="mono">{s.enrollment_no}</strong> },
    { key: 'name', header: 'Name', cell: (s) => s.name },
    { key: 'email', header: 'Email', cell: (s) => s.email || <span className="text-muted">—</span> },
    { key: 'batch', header: 'Batch', cell: (s) => s.batch.name },
    { key: 'login', header: 'Login', cell: (s) => (s.has_login ? <Badge tone="success" dot>Has login</Badge> : <Badge>No login</Badge>) },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (s) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(s)} aria-label={`Edit ${s.enrollment_no} ${s.name}`}><Icon name="edit" size={15} /> Edit</Button>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(s)} aria-label={`Delete ${s.enrollment_no} ${s.name}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function confirmDelete() {
    setBusy(true);
    try {
      const result = await studentsApi.remove(toDelete.id);
      toast({
        tone: 'success',
        title: 'Student deleted',
        message: result?.login_disabled ? `${toDelete.name} — their login account was disabled.` : toDelete.name,
      });
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete the student', message: err.message });
    } finally {
      setBusy(false);
      setToDelete(null);
      list.reload();
    }
  }

  return (
    <>
      <PageHeader
        title="Students"
        description="Manage student records and assign each student to a batch. Only administrators can see this list."
        breadcrumbs={crumbsFor('admin', 'Students')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add student</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search students by enrollment number, name or email" placeholder="Search number, name or email" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Batch" value={list.filters.batch_id} onChange={(v) => list.setFilter('batch_id', v)} options={batchOptions} />
          <FilterSelect label="Semester" value={list.filters.semester_no} onChange={(v) => list.setFilter('semester_no', v)} options={SEMESTER_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Students"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No students yet"
          emptyText="Add students and place each one in a batch. Create the batch first if you have not already."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add student</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="students" />
      </Card>

      {formFor !== undefined && <StudentFormDialog student={formFor} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone="danger"
        title="Delete this student?"
        message={toDelete && `${toDelete.enrollment_no} · ${toDelete.name} will be permanently removed.${toDelete.has_login ? ' Their login account will also be disabled, so they can no longer sign in.' : ''} This cannot be undone.`}
        confirmLabel="Delete"
        busy={busy}
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
