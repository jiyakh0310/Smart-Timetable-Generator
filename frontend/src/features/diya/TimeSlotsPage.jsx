// Diya - R6 Time-Slot Management screen. Reference implementation of the shared list/table pattern.
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Badge, Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import TimeSlotFormDialog from './TimeSlotFormDialog.jsx';
import { DAYS, LIST_PATH, timeSlotsApi } from './timeSlots.js';

const DAY_OPTIONS = [{ value: '', label: 'All days' }, ...DAYS.map((d) => ({ value: String(d.value), label: d.name }))];
const TYPE_OPTIONS = [{ value: '', label: 'All types' }, { value: 'class', label: 'Class period' }, { value: 'break', label: 'Break' }];
const STATUS_OPTIONS = [{ value: '', label: 'Any status' }, { value: 'true', label: 'Active' }, { value: 'false', label: 'Disabled' }];
const INITIAL_FILTERS = { day: '', slot_type: '', active: '' };

const describe = (slot) => `${slot.day_name}, Period ${slot.period_no} (${slot.start_time}-${slot.end_time})`;

function usageText(usage) {
  const parts = [];
  if (usage.timetable_entries) parts.push(`${usage.timetable_entries} timetable entr${usage.timetable_entries === 1 ? 'y' : 'ies'}`);
  if (usage.faculty_availability) parts.push(`${usage.faculty_availability} faculty availability record${usage.faculty_availability === 1 ? '' : 's'}`);
  return parts.join(' and ');
}

export default function TimeSlotsPage() {
  const toast = useToast();
  const list = useListQuery(LIST_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined); // undefined = closed, null = create, slot = edit
  const [toDelete, setToDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const columns = [
    { key: 'day', header: 'Day', cell: (s) => <strong>{s.day_name}</strong> },
    { key: 'period', header: 'Period', cell: (s) => `Period ${s.period_no}` },
    { key: 'time', header: 'Time', cell: (s) => <span className="nowrap">{s.start_time} – {s.end_time}</span> },
    { key: 'type', header: 'Type', cell: (s) => <Badge tone={s.slot_type === 'break' ? 'warning' : 'primary'}>{s.slot_type === 'break' ? 'Break' : 'Class'}</Badge> },
    {
      key: 'status',
      header: 'Status',
      cell: (s) => (
        <span className="badge-row">
          <Badge tone={s.is_active ? 'success' : 'neutral'} dot>{s.is_active ? 'Active' : 'Disabled'}</Badge>
          {s.in_use && <Badge tone="info">In use</Badge>}
        </span>
      ),
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

  function closeForm() { setFormFor(undefined); }
  function saved() { closeForm(); list.reload(); }

  async function confirmDelete() {
    setBusy(true);
    try {
      if (toDelete.in_use) {
        await timeSlotsApi.update(toDelete.id, { is_active: false });
        toast({ tone: 'success', title: 'Time slot disabled', message: describe(toDelete) });
      } else {
        await timeSlotsApi.remove(toDelete.id);
        toast({ tone: 'success', title: 'Time slot deleted', message: describe(toDelete) });
      }
      setToDelete(null);
      list.reload();
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not complete the action', message: err.message });
      setToDelete(null);
      list.reload();
    } finally {
      setBusy(false);
    }
  }

  const inUse = toDelete?.in_use;
  const alreadyDisabled = inUse && !toDelete.is_active;

  return (
    <>
      <PageHeader
        title="Time slots"
        description="Define the working days, periods and breaks that timetables are built on."
        breadcrumbs={crumbsFor('admin', 'Time slots')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add time slots</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search time slots by period number or time" placeholder="Search period or time, e.g. 3 or 09:" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Day" value={list.filters.day} onChange={(v) => list.setFilter('day', v)} options={DAY_OPTIONS} />
          <FilterSelect label="Type" value={list.filters.slot_type} onChange={(v) => list.setFilter('slot_type', v)} options={TYPE_OPTIONS} />
          <FilterSelect label="Status" value={list.filters.active} onChange={(v) => list.setFilter('active', v)} options={STATUS_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Time slots"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No time slots yet"
          emptyText="Add the periods your institution uses each day. A timetable cannot be generated without them."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> Add time slots</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="time slots" />
      </Card>

      {formFor !== undefined && <TimeSlotFormDialog slot={formFor} onClose={closeForm} onSaved={saved} />}

      <ConfirmDialog
        open={Boolean(toDelete)}
        tone={inUse ? 'primary' : 'danger'}
        title={inUse ? 'This time slot is in use' : 'Delete this time slot?'}
        message={
          inUse
            ? `${describe(toDelete)} is used by ${usageText(toDelete.usage)}, so it cannot be deleted.${alreadyDisabled ? ' It is already disabled, so it will not be used for new timetables.' : ' Disable it instead to stop it being scheduled.'}`
            : toDelete && `${describe(toDelete)} will be permanently removed. This cannot be undone.`
        }
        confirmLabel={alreadyDisabled ? 'OK' : inUse ? 'Disable slot' : 'Delete'}
        cancelLabel={alreadyDisabled ? 'Close' : 'Cancel'}
        busy={busy}
        onConfirm={alreadyDisabled ? () => setToDelete(null) : confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </>
  );
}
