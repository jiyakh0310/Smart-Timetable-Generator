import { Button, EmptyState, Notice, Skeleton } from '../ui';

/*
 * Accessible, responsive data table with built-in loading / error / empty states.
 *
 *   columns: [{ key, header, cell(row), align?: 'right', srOnlyHeader?: true }]
 *   state:   initialLoad (skeleton rows) | error (message + Retry) | no rows (empty state) | rows
 *   While reloading with rows already on screen, the rows stay visible (dimmed) and aria-busy is set.
 */
export default function DataTable({
  caption,
  columns,
  rows,
  rowKey = (row) => row.id,
  loading = false,
  initialLoad = false,
  error = '',
  onRetry,
  filtered = false,
  onClearFilters,
  emptyTitle = 'Nothing here yet',
  emptyText,
  emptyAction,
  skeletonRows = 5,
}) {
  const span = columns.length;
  const alignClass = (c) => (c.align === 'right' ? 'cell-right' : undefined);

  let body;
  if (error) {
    body = (
      <tr>
        <td colSpan={span}>
          <div className="table-state">
            <Notice tone="danger">{error}</Notice>
            {onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}
          </div>
        </td>
      </tr>
    );
  } else if (initialLoad) {
    body = Array.from({ length: skeletonRows }, (_, i) => (
      <tr key={i} aria-hidden="true">
        {columns.map((c) => <td key={c.key}><Skeleton height={16} width={c.align === 'right' ? '60%' : '80%'} /></td>)}
      </tr>
    ));
  } else if (rows.length === 0) {
    body = (
      <tr>
        <td colSpan={span}>
          {filtered ? (
            <EmptyState title="No results match your search" icon="info"
              action={onClearFilters && <Button variant="secondary" onClick={onClearFilters}>Clear search and filters</Button>}>
              Try a different search or remove a filter.
            </EmptyState>
          ) : (
            <EmptyState title={emptyTitle} icon="layers" action={emptyAction}>{emptyText}</EmptyState>
          )}
        </td>
      </tr>
    );
  } else {
    body = rows.map((row) => (
      <tr key={rowKey(row)}>
        {columns.map((c) => <td key={c.key} className={alignClass(c)}>{c.cell(row)}</td>)}
      </tr>
    ));
  }

  return (
    <div className={`table-wrap${loading && !initialLoad && !error ? ' is-refreshing' : ''}`} aria-busy={loading}>
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={alignClass(c)}>
                {c.srOnlyHeader ? <span className="sr-only">{c.header}</span> : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{body}</tbody>
      </table>
    </div>
  );
}
