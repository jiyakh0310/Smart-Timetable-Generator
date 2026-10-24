import { Badge, Card, EmptyState } from './ui';

// Honest placeholder for a feature whose backend does not exist yet. Never shows fake data.
export default function FeaturePending({ title, icon, req, milestone, children }) {
  return (
    <Card title={title} action={<Badge tone="warning">Not available yet · {milestone}</Badge>}>
      <EmptyState title="Not available yet" icon={icon}>
        {children} <span className="nowrap">({req})</span>
      </EmptyState>
    </Card>
  );
}
