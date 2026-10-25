import { useRef } from 'react';
import useStackedLayout from '../../hooks/useStackedLayout.js';
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
  const wrapRef = useRef(null);
  const stacked = useStackedLayout(wrapRef, columns.length, rows);
  const alignClass = (c) => (c.align === 'right' ? 'cell-right' : undefined);

  let body;
  if (error) {
    body = (
      <tr>
        <td colSpan={span} className="cell-state">
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
        {columns.map((c) => <td key={c.key} className="cell-skeleton"><Skeleton height={16} width={c.align === 'right' ? '60%' : '80%'} /></td>)}
      </tr>
    ));
  } else if (rows.length === 0) {
    body = (
      <tr>
        <td colSpan={span} className="cell-state">
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
      <tr key={rowKey(row)} role={stacked ? 'row' : undefined}>
        {columns.map((c, i) => (
          <td key={c.key} data-label={c.srOnlyHeader ? undefined : c.header} role={stacked ? 'cell' : undefined}
            className={[alignClass(c), i === 0 && !c.srOnlyHeader ? 'cell-title' : '', c.srOnlyHeader ? 'cell-actions' : ''].filter(Boolean).join(' ') || undefined}>
            {c.cell(row)}
          </td>
        ))}
      </tr>
    ));
  }

  return (
    <div ref={wrapRef} className={`table-wrap${stacked ? ' is-stacked' : ''}${loading && !initialLoad && !error ? ' is-refreshing' : ''}`} aria-busy={loading}>
      <table className="table" role={stacked ? 'table' : undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead role={stacked ? 'rowgroup' : undefined}>
          <tr role={stacked ? 'row' : undefined}>
            {columns.map((c) => (
              <th key={c.key} scope="col" role={stacked ? 'columnheader' : undefined} className={alignClass(c)}>
                {c.srOnlyHeader ? <span className="sr-only">{c.header}</span> : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role={stacked ? 'rowgroup' : undefined}>{body}</tbody>
      </table>
    </div>
  );
}
