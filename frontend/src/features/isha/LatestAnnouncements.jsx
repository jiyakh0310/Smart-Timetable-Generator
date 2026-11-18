// Isha - R19: the newest published announcements, for the Faculty and Student dashboards (real data, read-only).
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, EmptyState, Notice, Skeleton } from '../../components/ui';
import { api } from '../../services/api.js';
import { CategoryBadge } from './AnnouncementParts.jsx';
import { FEED_PATH, formatDate } from './announcements.js';

export default function LatestAnnouncements({ role, count = 3 }) {
  const [state, setState] = useState({ loading: true, error: '', items: [] });
  useEffect(() => {
    let live = true;
    api.get(`${FEED_PATH}?per_page=${count}`)
      .then((data) => live && setState({ loading: false, error: '', items: data.items }))
      .catch((err) => live && setState({ loading: false, error: err.message || 'Could not load announcements.', items: [] }));
    return () => { live = false; };
  }, [count]);

  const all = <Link to={`/${role}/announcements`}>View all</Link>;
  return (
    <Card title="Announcements" action={all}>
      {state.loading && <div role="status" aria-label="Loading announcements"><Skeleton height={16} width="80%" /><Skeleton height={16} width="60%" /></div>}
      {state.error && <Notice tone="danger">{state.error}</Notice>}
      {!state.loading && !state.error && state.items.length === 0 && (
        <EmptyState title="No announcements yet" icon="bell">Timetable and classroom changes will be posted here.</EmptyState>
      )}
      {state.items.length > 0 && (
        <ul className="announce-mini">
          {state.items.map((a) => (
            <li key={a.id}>
              <CategoryBadge category={a.category} />
              <Link to={`/${role}/announcements`}>{a.title}</Link>
              <small className="text-muted">{formatDate(a.published_at)}</small>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
