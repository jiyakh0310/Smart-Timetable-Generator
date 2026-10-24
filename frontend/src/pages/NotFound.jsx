import { ButtonLink, EmptyState, PageHeader } from '../components/ui';

export default function NotFound({ standalone = false }) {
  return (
    <div className={standalone ? 'page page-standalone' : undefined}>
      <PageHeader title="Page not found" />
      <EmptyState title="We can't find that page" icon="alert" action={<ButtonLink to="/" variant="primary">Go to your dashboard</ButtonLink>}>
        The address may be wrong, or the page may have moved.
      </EmptyState>
    </div>
  );
}
