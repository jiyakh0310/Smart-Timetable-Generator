// Diya - R4 Subject/Course Management screen (built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import SubjectFormDialog from './SubjectFormDialog.jsx';
import { ROOM_LABEL, SUBJECTS_PATH, MAX, sessionsText, subjectsApi } from './subjects.js';
import useDepartments from './useDepartments.js';

const SEMESTER_OPTIONS = [{ value: '', label: 'All semesters' }, ...Array.from({ length: MAX.semester }, (_, i) => ({ value: String(i + 1), label: `Semester ${i + 1}` }))];
const TYPE_OPTIONS = [{ value: '', label: 'All types' }, { value: 'theory', label: 'Theory' }, { value: 'lab', label: 'Lab' }];
const INITIAL_FILTERS = { department_id: '', semester_no: '', class_type: '' };

const describe = (s) => `${s.code} ${s.name}`;

export default function SubjectsPage() {
  const toast = useToast();
  const departments = useDepartments();
  const list = useListQuery(SUBJECTS_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, subject = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const departmentOptions = [{ value: '', label: 'All departments' }, ...departments.items.map((d) => ({ value: String(d.id), label: d.code }))];

  const columns = [
    { key: 'code', header: 'Code', cell: (s) => <strong className="mono">{s.code}</strong> },
    { key: 'name', header: 'Subject', cell: (s) => (<span className="cell-stack"><span>{s.name}</span><small className="text-muted">{s.department.code}</small></span>) },
    { key: 'semester', header: 'Sem', cell: (s) => s.semester_no },
    { key: 'credits', header: 'Credits', cell: (s) => s.credits },
    { key: 'hours', header: 'Weekly hours', cell: (s) => (<span className="cell-stack"><span>{s.weekly_hours} h</span><small className="text-muted">{sessionsText(s)}</small></span>) },
    { key: 'type', header: 'Type', cell: (s) => <Badge tone={s.class_type === 'lab' ? 'info' : 'primary'}>{s.class_type === 'lab' ? 'Lab' : 'Theory'}</Badge> },
    { key: 'room', header: 'Room', cell: (s) => (s.required_room_type ? ROOM_LABEL[s.required_room_type] : '—') },
    {
      key: 'assigned',
      header: 'Teaching',
      cell: (s) => (s.in_use
        ? <Badge tone="success" dot>{s.usage.teaching_assignments} batch{s.usage.teaching_assignments === 1 ? '' : 'es'}</Badge>
        : <Badge>Not assigned</Badge>),
    },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (s) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(s)} aria-label={`Edit ${describe(s)}`}><Icon name="edit" size={15} /> Edit</Button>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(s)} aria-label={`Delete ${describe(s)}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function confirmDelete() {
    setBusy(true);
    try {
      await subjectsApi.remove(toDelete.id);
      toast({ tone: 'success', title: 'Subject deleted', message: describe(toDelete) });
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete the subject', message: err.message });
    } finally {
      setBusy(false);
      setToDelete(null);
      list.reload();
    }
  }

  const inUse = toDelete?.in_use;
  const n = toDelete?.usage.teaching_assignments;

  return (
    <>
      <PageHeader
        title="Subjects"
        description="Manage the subjects (courses) taught each semester: credits, weekly hours and whether they are theory or lab."
        breadcrumbs={crumbsFor('admin', 'Subjects')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add subject</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search subjects by code or name" placeholder="Search by code or name" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Department" value={list.filters.department_id} onChange={(v) => list.setFilter('department_id', v)} options={departmentOptions} />
          <FilterSelect label="Semester" value={list.filters.semester_no} onChange={(v) => list.setFilter('semester_no', v)} options={SEMESTER_OPTIONS} />
          <FilterSelect label="Type" value={list.filters.class_type} onChange={(v) => list.setFilter('class_type', v)} options={TYPE_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Subjects"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No subjects yet"
          emptyText="Add the subjects your institution teaches. They are needed before faculty can be assigned and a timetable generated."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add subject</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="subjects" />
      </Card>

      {formFor !== undefined && <SubjectFormDialog subject={formFor} departments={departments.items} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This subject is in use' : 'Delete this subject?'}
        message={
          inUse
            ? `${describe(toDelete)} is used by ${n} teaching assignment${n === 1 ? '' : 's'}, so it cannot be deleted. Remove those assignments first.`
            : toDelete && `${describe(toDelete)} will be permanently removed. This cannot be undone.`
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
