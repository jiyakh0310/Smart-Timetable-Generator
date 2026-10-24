// Isha - R2 Faculty management screen (Admin only; built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, ButtonLink, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import useDepartments from '../diya/useDepartments.js';
import FacultyFormDialog from './FacultyFormDialog.jsx';
import ResetPasswordDialog from './ResetPasswordDialog.jsx';
import { FACULTY_PATH, facultyApi } from './faculty.js';

const STATUS_OPTIONS = [{ value: '', label: 'Any status' }, { value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }];
const INITIAL_FILTERS = { department_id: '', active: '' };

function availabilityText({ unavailable, preferred }) {
  const parts = [];
  if (unavailable) parts.push(`${unavailable} unavailable`);
  if (preferred) parts.push(`${preferred} preferred`);
  return parts.length ? parts.join(' · ') : 'Fully available';
}

export default function FacultyPage() {
  const toast = useToast();
  const departments = useDepartments();
  const list = useListQuery(FACULTY_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, faculty = edit
  const [resetFor, setResetFor] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const departmentOptions = [{ value: '', label: 'All departments' }, ...departments.items.map((d) => ({ value: String(d.id), label: d.code }))];

  const columns = [
    { key: 'code', header: 'Code', cell: (f) => <strong className="mono">{f.employee_code}</strong> },
    { key: 'name', header: 'Faculty', cell: (f) => (<span className="cell-stack"><strong>{f.name}</strong><small className="text-muted">{f.email}</small></span>) },
    { key: 'dept', header: 'Dept', cell: (f) => f.department.code },
    { key: 'designation', header: 'Designation', cell: (f) => f.designation || <span className="text-muted">—</span> },
    { key: 'hours', header: 'Weekly limit', cell: (f) => `${f.max_weekly_hours} h` },
    {
      key: 'teaching',
      header: 'Teaching',
      cell: (f) => (f.usage.teaching_assignments
        ? <Badge tone="success" dot>{f.usage.teaching_assignments} assignment{f.usage.teaching_assignments === 1 ? '' : 's'}</Badge>
        : <Badge>None</Badge>),
    },
    { key: 'availability', header: 'Availability', cell: (f) => <span className="text-muted">{availabilityText(f.availability)}</span> },
    { key: 'status', header: 'Status', cell: (f) => <Badge tone={f.is_active ? 'success' : 'neutral'} dot>{f.is_active ? 'Active' : 'Inactive'}</Badge> },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (f) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(f)} aria-label={`Edit ${f.employee_code} ${f.name}`}><Icon name="edit" size={15} /> Edit</Button>
          <ButtonLink to={`/admin/availability?faculty=${f.id}`} variant="secondary" size="sm" aria-label={`Availability of ${f.name}`}><Icon name="clock" size={15} /> Availability</ButtonLink>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(f)} aria-label={`Delete ${f.employee_code} ${f.name}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };
  const startReset = (faculty) => { closeForm(); setResetFor(faculty); };

  async function confirmDelete() {
    setBusy(true);
    try {
      if (toDelete.in_use) {
        await facultyApi.update(toDelete.id, { is_active: false });
        toast({ tone: 'success', title: 'Faculty member deactivated', message: `${toDelete.name} can no longer sign in. Their records are kept.` });
      } else {
        await facultyApi.remove(toDelete.id);
        toast({ tone: 'success', title: 'Faculty member deleted', message: toDelete.name });
      }
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not complete the action', message: err.message });
    } finally {
      setBusy(false);
      setToDelete(null);
      list.reload();
    }
  }

  const inUse = toDelete?.in_use;
  const alreadyInactive = inUse && !toDelete.is_active;
  const n = toDelete?.usage.teaching_assignments;

  return (
    <>
      <PageHeader
        title="Faculty"
        description="Manage faculty members and their login accounts. Only administrators can see this list."
        breadcrumbs={crumbsFor('admin', 'Faculty')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add faculty member</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search faculty by code, name or email" placeholder="Search code, name or email" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Department" value={list.filters.department_id} onChange={(v) => list.setFilter('department_id', v)} options={departmentOptions} />
          <FilterSelect label="Status" value={list.filters.active} onChange={(v) => list.setFilter('active', v)} options={STATUS_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Faculty"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No faculty members yet"
          emptyText="Add your faculty. Each one gets a login account so they can view their timetable once it is published."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add faculty member</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="faculty members" />
      </Card>

      {formFor !== undefined && (
        <FacultyFormDialog faculty={formFor} departments={departments.items} onClose={closeForm} onSaved={saved} onResetPassword={startReset} />
      )}
      {resetFor && <ResetPasswordDialog faculty={resetFor} onClose={() => setResetFor(null)} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This faculty member is in use' : 'Delete this faculty member?'}
        message={
          inUse
            ? `${toDelete.name} has ${n} teaching assignment${n === 1 ? '' : 's'}, so they cannot be deleted.${alreadyInactive ? ' They are already inactive: they cannot sign in and all records are kept.' : ' Deactivate them instead: their login is disabled and all records are kept.'}`
            : toDelete && `${toDelete.name} will be permanently removed together with their login account and availability settings. This cannot be undone.`
        }
        confirmLabel={alreadyInactive ? 'OK' : inUse ? 'Deactivate' : 'Delete'}
        showCancel={!alreadyInactive}
        busy={busy}
        onConfirm={alreadyInactive ? () => setToDelete(null) : confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
