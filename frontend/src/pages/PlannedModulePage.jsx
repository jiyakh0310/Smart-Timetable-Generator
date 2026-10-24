import { crumbsFor } from '../app/navConfig.js';
import { Badge, Card, PageHeader, PriorityBadge } from '../components/ui';

// Shown for screens whose feature is not built yet. States plainly who owns it and when it lands.
export default function PlannedModulePage({ item, role }) {
  return (
    <>
      <PageHeader title={item.label} description={item.blurb} breadcrumbs={crumbsFor(role, item.label)} />
      <Card>
        <div className="planned">
          <div className="planned-main">
            <Badge tone="warning" dot>Not available yet</Badge>
            <h2>This feature is planned for {item.milestone}</h2>
            <p className="text-muted">
              It is not built yet, so nothing on this page is functional. It will use real data from the database when it is released.
            </p>
          </div>
          <dl className="meta-list">
            <div><dt>Requirement</dt><dd>{item.req}</dd></div>
            <div><dt>Priority</dt><dd><PriorityBadge priority={item.priority} /></dd></div>
            <div><dt>Owner</dt><dd>{item.owner}</dd></div>
            <div><dt>Milestone</dt><dd>{item.milestone}</dd></div>
          </dl>
        </div>
      </Card>
    </>
  );
}
