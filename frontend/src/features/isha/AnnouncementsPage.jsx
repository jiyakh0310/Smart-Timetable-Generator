// Isha - R19 Announcements management (Admin only): list, filter, search, view, create, edit, publish / unpublish, delete.
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { DataTable, FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Button, Card, ConfirmDialog, Icon, PageHeader, useToast } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import AnnouncementFormDialog from './AnnouncementFormDialog.jsx';
import { AnnouncementDetailDialog, CategoryBadge, StatusPill } from './AnnouncementParts.jsx';
import { ANNOUNCEMENTS_PATH, announcementsApi, CATEGORY_OPTIONS, excerpt, formatDate, STATUS_OPTIONS } from './announcements.js';

const INITIAL_FILTERS = { status: '', category: '' };

export default function AnnouncementsPage() {
  const toast = useToast();
  const list = useListQuery(ANNOUNCEMENTS_PATH, { perPage: 10, initialFilters: INITIAL_FILTERS });
  const [formFor, setFormFor] = useState(undefined);   // undefined = closed, null = create, item = edit
  const [viewing, setViewing] = useState(null);
  const [confirm, setConfirm] = useState(null);        // { kind: 'publish' | 'unpublish' | 'delete', item }
  const [busy, setBusy] = useState(false);

  const columns = [
    { key: 'title', header: 'Announcement', cell: (a) => (<span className="cell-stack"><strong>{a.title}</strong><small className="text-muted announce-snippet">{excerpt(a.message, 110)}</small></span>) },
    { key: 'category', header: 'Category', cell: (a) => <CategoryBadge category={a.category} /> },
    { key: 'status', header: 'Status', cell: (a) => <StatusPill status={a.status} /> },
    { key: 'published', header: 'Published', cell: (a) => formatDate(a.published_at) },
    { key: 'author', header: 'Author', cell: (a) => a.author.name },
    {
      key: 'actions',
      header: 'Actions',
      srOnlyHeader: true,
      align: 'right',
      cell: (a) => (
        <span className="row-actions">
          <Button variant="secondary" size="sm" onClick={() => setViewing(a)} aria-label={`View ${a.title}`}>View</Button>
          <Button variant="secondary" size="sm" onClick={() => setFormFor(a)} aria-label={`Edit ${a.title}`}><Icon name="edit" size={15} /> Edit</Button>
          {a.status === 'published'
            ? <Button variant="ghost" size="sm" onClick={() => setConfirm({ kind: 'unpublish', item: a })} aria-label={`Unpublish ${a.title}`}>Unpublish</Button>
            : <Button variant="ghost" size="sm" onClick={() => setConfirm({ kind: 'publish', item: a })} aria-label={`Publish ${a.title}`}>Publish</Button>}
          <Button variant="ghost" size="sm" className="btn-danger-text" onClick={() => setConfirm({ kind: 'delete', item: a })} aria-label={`Delete ${a.title}`}><Icon name="trash" size={15} /> Delete</Button>
        </span>
      ),
    },
  ];

  const closeForm = () => setFormFor(undefined);
  const saved = () => { closeForm(); list.reload(); };

  async function runConfirmed() {
    const { kind, item } = confirm;
    setBusy(true);
    try {
      if (kind === 'publish') await announcementsApi.publish(item.id);
      else if (kind === 'unpublish') await announcementsApi.unpublish(item.id);
      else await announcementsApi.remove(item.id);
      toast({ tone: 'success', title: { publish: 'Announcement published', unpublish: 'Moved back to drafts', delete: 'Announcement deleted' }[kind], message: item.title });
    } catch (err) {
      toast({ tone: 'danger', title: `Could not ${kind} the announcement`, message: err.message });
    } finally {
      setBusy(false);
      setConfirm(null);
      list.reload();
    }
  }

  const COPY = {
    publish: { title: 'Publish this announcement?', confirm: 'Publish', message: (i) => `“${i.title}” becomes visible to all faculty and students.` },
    unpublish: { title: 'Move this announcement back to drafts?', confirm: 'Unpublish', message: (i) => `“${i.title}” stops being visible to faculty and students. You can publish it again later.` },
    delete: { title: 'Delete this announcement?', confirm: 'Delete', message: (i) => `“${i.title}” will be permanently removed${i.status === 'published' ? ' and disappear for faculty and students' : ''}. This cannot be undone.` },
  };
  const copy = confirm ? COPY[confirm.kind] : null;

  return (
    <>
      <PageHeader
        title="Announcements"
        description="Publish timetable changes and academic notices. Drafts are visible only to administrators; published announcements are visible to all faculty and students."
        breadcrumbs={crumbsFor('admin', 'Announcements')}
        actions={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> New announcement</Button>}
      />

      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search announcements by title or content" placeholder="Search title or content" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Category" value={list.filters.category} onChange={(v) => list.setFilter('category', v)} options={CATEGORY_OPTIONS} />
          <FilterSelect label="Status" value={list.filters.status} onChange={(v) => list.setFilter('status', v)} options={STATUS_OPTIONS} />
        </TableToolbar>

        <DataTable
          caption="Announcements"
          columns={columns}
          rows={list.items}
          loading={list.loading}
          initialLoad={list.initialLoad}
          error={list.error}
          onRetry={list.reload}
          filtered={list.hasActiveFilters}
          onClearFilters={list.clearFilters}
          emptyTitle="No announcements yet"
          emptyText="Write the first announcement. Save it as a draft, or publish it for faculty and students straight away."
          emptyAction={<Button onClick={() => setFormFor(null)}><Icon name="plus" size={16} /> New announcement</Button>}
        />
        <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="announcements" />
      </Card>

      {formFor !== undefined && <AnnouncementFormDialog announcement={formFor} onClose={closeForm} onSaved={saved} />}
      {viewing && (
        <AnnouncementDetailDialog
          item={viewing}
          onClose={() => setViewing(null)}
          actions={<Button variant="secondary" onClick={() => { const item = viewing; setViewing(null); setFormFor(item); }}><Icon name="edit" size={15} /> Edit</Button>}
        />
      )}

      <ConfirmDialog
        open={Boolean(confirm)}
        tone={confirm?.kind === 'delete' ? 'danger' : confirm?.kind === 'publish' ? 'success' : 'primary'}
        title={copy?.title ?? ''}
        message={confirm ? copy.message(confirm.item) : ''}
        confirmLabel={copy?.confirm}
        busy={busy}
        onConfirm={runConfirmed}
        onCancel={() => setConfirm(null)}
      />
    </>
  );
}
