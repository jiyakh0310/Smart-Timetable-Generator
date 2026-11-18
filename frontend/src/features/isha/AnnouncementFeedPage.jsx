// Isha - R19 Announcements for Faculty and Students: read-only, published announcements only.
import { useState } from 'react';
import { crumbsFor } from '../../app/navConfig.js';
import { FilterSelect, Pagination, SearchBox, TableToolbar } from '../../components/data';
import { Button, Card, EmptyState, Notice, PageHeader, Skeleton } from '../../components/ui';
import useListQuery from '../../hooks/useListQuery.js';
import { AnnouncementDetailDialog, CategoryBadge, MetaLine } from './AnnouncementParts.jsx';
import { CATEGORY_OPTIONS, excerpt, FEED_PATH } from './announcements.js';

const INITIAL_FILTERS = { category: '' };

function FeedSkeleton() {
  return (
    <div className="announce-list" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="announce-card">
          <Skeleton height={14} width="30%" />
          <Skeleton height={20} width="70%" />
          <Skeleton height={14} width="95%" />
        </div>
      ))}
    </div>
  );
}

export function AnnouncementFeed({ role }) {
  const list = useListQuery(FEED_PATH, { perPage: 8, initialFilters: INITIAL_FILTERS });
  const [open, setOpen] = useState(null);

  let body;
  if (list.initialLoad) {
    body = <div role="status" aria-label="Loading announcements"><FeedSkeleton /></div>;
  } else if (list.error) {
    body = (
      <div className="announce-state">
        <Notice tone="danger">{list.error}</Notice>
        <Button variant="secondary" onClick={list.reload}>Try again</Button>
      </div>
    );
  } else if (list.items.length === 0) {
    body = list.hasActiveFilters ? (
      <EmptyState title="No announcements match your search" icon="info" action={<Button variant="secondary" onClick={list.clearFilters}>Clear search and filters</Button>}>
        Try a different word or another category.
      </EmptyState>
    ) : (
      <EmptyState title="No announcements yet" icon="bell">
        Timetable changes and academic notices will appear here once the administrator publishes them.
      </EmptyState>
    );
  } else {
    body = (
      <ul className={`announce-list${list.loading ? ' is-refreshing' : ''}`} aria-busy={list.loading} aria-label="Announcements">
        {list.items.map((a) => (
          <li key={a.id}>
            <article className={`announce-card is-${a.category}`}>
              <div className="announce-card-top">
                <CategoryBadge category={a.category} />
                <MetaLine item={a} />
              </div>
              <h2 className="announce-title">{a.title}</h2>
              <p className="announce-excerpt">{excerpt(a.message)}</p>
              <Button variant="ghost" size="sm" onClick={() => setOpen(a)} aria-label={`Read ${a.title}`}>Read more</Button>
            </article>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <>
      <PageHeader
        title="Announcements"
        description="Timetable changes and academic notices from the administration."
        breadcrumbs={crumbsFor(role, 'Announcements')}
      />
      <Card flush>
        <TableToolbar hasActiveFilters={list.hasActiveFilters} onClear={list.clearFilters}>
          <SearchBox label="Search announcements" placeholder="Search announcements" value={list.search} onChange={list.setSearch} />
          <FilterSelect label="Category" value={list.filters.category} onChange={(v) => list.setFilter('category', v)} options={CATEGORY_OPTIONS} />
        </TableToolbar>
        <div className="announce-wrap">{body}</div>
        {!list.error && list.items.length > 0 && <Pagination page={list.page} pages={list.pages} total={list.total} perPage={list.perPage} onPageChange={list.setPage} itemLabel="announcements" />}
      </Card>
      {open && <AnnouncementDetailDialog item={{ ...open, status: undefined }} onClose={() => setOpen(null)} />}
    </>
  );
}

export const FacultyAnnouncementsPage = () => <AnnouncementFeed role="faculty" />;
export const StudentAnnouncementsPage = () => <AnnouncementFeed role="student" />;
