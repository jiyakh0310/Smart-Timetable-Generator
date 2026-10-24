import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import DataTable from './DataTable.jsx';
import Pagination from './Pagination.jsx';

const columns = [
  { key: 'name', header: 'Name', cell: (r) => r.name },
  { key: 'actions', header: 'Actions', srOnlyHeader: true, align: 'right', cell: (r) => <button type="button">Edit {r.name}</button> },
];
const base = { caption: 'People', columns, rows: [], loading: false, initialLoad: false, error: '' };

describe('DataTable', () => {
  it('renders rows with a caption and column headers', () => {
    render(<DataTable {...base} rows={[{ id: 1, name: 'Asha' }, { id: 2, name: 'Ben' }]} />);
    const table = screen.getByRole('table', { name: 'People' });
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Name', 'Actions']);
    expect(within(table).getByRole('button', { name: 'Edit Asha' })).toBeInTheDocument();
    expect(within(table).getAllByRole('row')).toHaveLength(3); // header + 2
  });

  it('shows placeholder rows (hidden from assistive tech) and aria-busy during the first load', () => {
    const { container } = render(<DataTable {...base} loading initialLoad />);
    expect(container.querySelectorAll('.skeleton').length).toBeGreaterThan(0);
    expect(container.querySelector('.table-wrap')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByText('Nothing here yet')).not.toBeInTheDocument();
  });

  it('keeps existing rows visible (dimmed) while refreshing', () => {
    const { container } = render(<DataTable {...base} rows={[{ id: 1, name: 'Asha' }]} loading />);
    expect(screen.getByText('Asha')).toBeInTheDocument();
    expect(container.querySelector('.table-wrap')).toHaveClass('is-refreshing');
  });

  it('shows the error and a working retry button', async () => {
    const onRetry = vi.fn();
    render(<DataTable {...base} error="Cannot reach the server." onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the server.');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('shows an empty state with a call to action when there is no data', () => {
    render(<DataTable {...base} emptyTitle="No people yet" emptyText="Add the first person." emptyAction={<button type="button">Add person</button>} />);
    expect(screen.getByRole('heading', { name: 'No people yet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add person' })).toBeInTheDocument();
  });

  it('shows a different empty state when a search/filter produced no results, with a way to clear it', async () => {
    const onClear = vi.fn();
    render(<DataTable {...base} filtered onClearFilters={onClear} emptyTitle="No people yet" />);
    expect(screen.getByRole('heading', { name: 'No results match your search' })).toBeInTheDocument();
    expect(screen.queryByText('No people yet')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /clear search and filters/i }));
    expect(onClear).toHaveBeenCalledOnce();
  });
});

describe('Pagination', () => {
  const setup = (props) => {
    const onPageChange = vi.fn();
    render(<Pagination page={2} pages={4} total={35} perPage={10} itemLabel="slots" onPageChange={onPageChange} {...props} />);
    return onPageChange;
  };

  it('describes the visible range and page', () => {
    setup();
    expect(screen.getByText(/11-20/)).toBeInTheDocument();
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument();
  });

  it('clips the last page range to the total', () => {
    setup({ page: 4 });
    expect(screen.getByText(/31-35/)).toBeInTheDocument();
  });

  it('navigates with Previous / Next', async () => {
    const onPageChange = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenLastCalledWith(3);
    await userEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(onPageChange).toHaveBeenLastCalledWith(1);
  });

  it('disables Previous on the first page and Next on the last', () => {
    setup({ page: 1 });
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled();
  });

  it('renders nothing when there are no items', () => {
    const { container } = render(<Pagination page={1} pages={1} total={0} perPage={10} onPageChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
