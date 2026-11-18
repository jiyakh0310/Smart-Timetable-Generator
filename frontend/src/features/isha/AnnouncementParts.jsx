// Isha - R19: small pieces shared by the admin screen, the faculty / student feed and the dashboard card.
import { Badge, Button, Dialog } from '../../components/ui';
import { CATEGORY, formatDate } from './announcements.js';

export function CategoryBadge({ category }) {
  const meta = CATEGORY[category] || CATEGORY.general;
  return <Badge tone={meta.tone} dot>{meta.label}</Badge>;
}

export function StatusPill({ status }) {
  return status === 'published' ? <Badge tone="success" dot>Published</Badge> : <Badge dot>Draft</Badge>;
}

// "Published 12 Nov 2026 · by Dr. Anita Verma"  (a draft has no publish date yet)
export function MetaLine({ item }) {
  return (
    <p className="announce-meta">
      {item.published_at ? `Published ${formatDate(item.published_at)}` : 'Not published yet'} · by {item.author.name}
    </p>
  );
}

// Full announcement in a dialog. `actions` lets the admin screen add Edit.
export function AnnouncementDetailDialog({ item, onClose, actions }) {
  return (
    <Dialog open title={item.title} onClose={onClose} wide initialFocus="first">
      <div className="announce-detail-badges">
        <CategoryBadge category={item.category} />
        {item.status && <StatusPill status={item.status} />}
      </div>
      <MetaLine item={item} />
      <div className="announce-body">{item.message}</div>
      <div className="dialog-actions">
        {actions}
        <Button variant="secondary" onClick={onClose}>Close</Button>
      </div>
    </Dialog>
  );
}
