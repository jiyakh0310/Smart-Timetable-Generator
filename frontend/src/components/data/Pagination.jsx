import { Button, Icon } from '../ui';

// "Showing 11-20 of 35" + Previous / Next. Hidden when there is nothing to page through.
export default function Pagination({ page, pages, total, perPage, onPageChange, itemLabel = 'items' }) {
  if (total === 0) return null;
  const from = (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  return (
    <nav className="pagination" aria-label="Pagination">
      <p className="pagination-summary" aria-live="polite">
        Showing <strong>{from}-{to}</strong> of <strong>{total}</strong> {itemLabel}
      </p>
      <div className="pagination-controls">
        <span className="pagination-page">Page {page} of {pages}</span>
        <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)} aria-label="Previous page">
          <Icon name="chevron-left" size={16} /> Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPageChange(page + 1)} aria-label="Next page">
          Next <Icon name="chevron-right" size={16} />
        </Button>
      </div>
    </nav>
  );
}
