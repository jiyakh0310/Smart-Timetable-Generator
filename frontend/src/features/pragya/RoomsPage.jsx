// Pragya - R5 Rooms & Labs screen (Admin only; built on the shared list/table pattern).
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import RoomFormDialog from './RoomFormDialog.jsx';
import { ROOMS_PATH, roomsApi, TYPE_LABEL } from './rooms.js';

const TYPE_OPTIONS = [{ value: '', label: 'All types' }, ...Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))];
const STATUS_OPTIONS = [{ value: '', label: 'Any status' }, { value: 'true', label: 'In service' }, { value: 'false', label: 'Out of service' }];
const CAPACITY_OPTIONS = [{ value: '', label: 'Any size' }, ...[30, 50, 60, 100].map((n) => ({ value: String(n), label: `${n}+ seats` }))];
const INITIAL_FILTERS = { room_type: '', available: '', min_capacity: '' };
const TYPE_TONE = { classroom: 'primary', lab: 'info', seminar_hall: 'warning', auditorium: 'warning' };

export default function RoomsPage() {
  const toast = useToast();
  const list = useListQuery(ROOMS_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, room = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const columns = [
    { key: 'code', header: 'Code', cell: (r) => <strong className="mono">{r.code}</strong> },
    { key: 'name', header: 'Room', cell: (r) => (<span className="cell-stack"><span>{r.name}</span><small className="text-muted">{r.location || '—'}</small></span>) },
    {
      key: 'type',
      header: 'Type',
      cell: (r) => (<span className="cell-stack"><span><Badge tone={TYPE_TONE[r.room_type]}>{TYPE_LABEL[r.room_type]}</Badge></span>{r.lab_type && <small className="text-muted">{r.lab_type}</small>}</span>),
    },
    { key: 'capacity', header: 'Seats', cell: (r) => <strong>{r.capacity}</strong> },
    { key: 'status', header: 'Status', cell: (r) => <Badge tone={r.is_available ? 'success' : 'danger'} dot>{r.is_available ? 'In service' : 'Out of service'}</Badge> },
    {
      key: 'usage',
      header: 'Timetables',
      cell: (r) => (r.in_use ? <Badge tone="info">{r.usage.timetable_entries} entr{r.usage.timetable_entries === 1 ? 'y' : 'ies'}</Badge> : <span className="text-muted">Not used</span>),
    },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (r) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setFormFor(r)} aria-label={`Edit ${r.code} ${r.name}`}><Icon name="edit" size={15} /> Edit</Button>
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setToDelete(r)} aria-label={`Delete ${r.code} ${r.name}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function confirmDelete() {
    setBusy(true);
    try {
      await roomsApi.remove(toDelete.id);
      toast({ tone: 'success', title: 'Room deleted', message: `${toDelete.code} · ${toDelete.name}` });
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not delete the room', message: err.message });
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
        title="Rooms & labs"
        description="Manage classrooms, laboratories and halls. Capacity and type decide which classes a room can host."
        breadcrumbs={crumbsFor('admin', 'Rooms & labs')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add room</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search rooms by code, name or location" placeholder="Search code, name or location" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Type" value={list.filters.room_type} onChange={(v) => list.setFilter('room_type', v)} options={TYPE_OPTIONS} />
          <FilterSelect label="Size" value={list.filters.min_capacity} onChange={(v) => list.setFilter('min_capacity', v)} options={CAPACITY_OPTIONS} />
          <FilterSelect label="Status" value={list.filters.available} onChange={(v) => list.setFilter('available', v)} options={STATUS_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Rooms and laboratories"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No rooms yet"
          emptyText="Add your classrooms and laboratories. A timetable cannot be generated without rooms."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add room</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="rooms" />
      </Card>

      {formFor !== undefined && <RoomFormDialog room={formFor} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This room is in use' : 'Delete this room?'}
        message={
          inUse
            ? `${toDelete.code} is used by ${toDelete.usage.timetable_entries} timetable entr${toDelete.usage.timetable_entries === 1 ? 'y' : 'ies'}, so it cannot be deleted. Mark it out of service instead (Edit).`
            : toDelete && `${toDelete.code} · ${toDelete.name} will be permanently removed. This cannot be undone.`
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
