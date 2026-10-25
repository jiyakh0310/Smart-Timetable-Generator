import { act, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DataTable from './DataTable.jsx';

// jsdom has no layout, so the wrapper width, the table's natural width and ResizeObserver are all controlled here.
let width;
let naturalWidth;
let observers;
let clientDescriptor;
let scrollDescriptor;

beforeEach(() => {
  width = 1200;
  naturalWidth = 0;
  observers = [];
  vi.stubGlobal('ResizeObserver', class {
    constructor(cb) { this.cb = cb; observers.push(this); }
    observe() {}
    disconnect() {}
  });
  clientDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
  scrollDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollWidth');
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => width });
  Object.defineProperty(Element.prototype, 'scrollWidth', { configurable: true, get() { return this.tagName === 'TABLE' ? naturalWidth : 0; } });
});
afterEach(() => {
  vi.unstubAllGlobals();
  if (clientDescriptor) Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientDescriptor); else delete HTMLElement.prototype.clientWidth;
  if (scrollDescriptor) Object.defineProperty(Element.prototype, 'scrollWidth', scrollDescriptor); else delete Element.prototype.scrollWidth;
});

const columns = [
  { key: 'code', header: 'Code', cell: (r) => <strong>{r.code}</strong> },
  { key: 'name', header: 'Name', cell: (r) => r.name },
  { key: 'status', header: 'Status', cell: (r) => <span className="badge">{r.status}</span> },
  { key: 'actions', header: 'Actions', srOnlyHeader: true, cell: () => <button type="button">Edit</button> },
];
const rows = [{ id: 1, code: 'F001', name: 'Dr. Rakesh Sharma', status: 'Active' }, { id: 2, code: 'F002', name: 'Dr. Meera Iyer', status: 'Inactive' }];
const renderTable = (props = {}) => render(<DataTable caption="Faculty" columns={columns} rows={rows} {...props} />);
const wrapper = (container) => container.querySelector('.table-wrap');
const resize = (w) => act(() => { width = w; observers.forEach((o) => o.cb([{ contentRect: { width: w } }])); });

describe('DataTable - labelled cells', () => {
  it('every data cell carries its column header as a label; the first is the card title; the action cell is marked', () => {
    const { container } = renderTable();
    const cells = container.querySelectorAll('tbody tr:first-child td');
    expect([...cells].map((c) => c.getAttribute('data-label'))).toEqual(['Code', 'Name', 'Status', null]);
    expect(cells[0]).toHaveClass('cell-title');
    expect(cells[3]).toHaveClass('cell-actions');
  });

  it('empty, error-free loading and filtered states use full-width state cells', () => {
    const { container, rerender } = renderTable({ rows: [], emptyTitle: 'Nothing here' });
    expect(container.querySelector('td.cell-state')).toBeInTheDocument();
    rerender(<DataTable caption="Faculty" columns={columns} rows={[]} initialLoad loading />);
    expect(container.querySelectorAll('td.cell-skeleton')).toHaveLength(columns.length * 5);
  });
});

describe('DataTable - stacked cards', () => {
  it('stays a normal table where the columns fit', () => {
    const { container } = renderTable();
    expect(wrapper(container)).not.toHaveClass('is-stacked');
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    expect(container.querySelector('table')).not.toHaveAttribute('role');
  });

  it('becomes cards when the container is narrower than the columns need', () => {
    width = 300;
    const { container } = renderTable();
    expect(wrapper(container)).toHaveClass('is-stacked');
  });

  it('keeps table semantics for assistive technology while stacked', () => {
    width = 300;
    const { container } = renderTable();
    expect(container.querySelector('table')).toHaveAttribute('role', 'table');
    expect(screen.getAllByRole('row')).toHaveLength(3);
    expect(screen.getAllByRole('cell').length).toBe(8);
    expect(screen.getAllByRole('columnheader')).toHaveLength(4);
    expect(within(screen.getAllByRole('row')[1]).getByRole('button', { name: 'Edit' })).toBeInTheDocument(); // actions stay available
  });

  it('follows the container as it is resized, both ways', () => {
    const { container } = renderTable();
    expect(wrapper(container)).not.toHaveClass('is-stacked');
    resize(320);
    expect(wrapper(container)).toHaveClass('is-stacked');
    resize(1100);
    expect(wrapper(container)).not.toHaveClass('is-stacked');
  });

  it('also stacks when the real table turns out to overflow, and does not flip back until there is more room', () => {
    width = 700;
    naturalWidth = 900; // wide content (long unbreakable text, many badges...) that the column count did not predict
    const { container } = renderTable();
    expect(wrapper(container)).toHaveClass('is-stacked');
    resize(650);
    expect(wrapper(container)).toHaveClass('is-stacked');
    naturalWidth = 0;
    resize(1000); // wider than where it overflowed, and now it fits
    expect(wrapper(container)).not.toHaveClass('is-stacked');
  });

  it('measures again when the data changes', () => {
    width = 700;
    naturalWidth = 900;
    const { container, rerender } = renderTable();
    expect(wrapper(container)).toHaveClass('is-stacked');
    naturalWidth = 400; // the new rows are narrower
    rerender(<DataTable caption="Faculty" columns={columns} rows={[rows[0]]} />);
    expect(wrapper(container)).not.toHaveClass('is-stacked');
  });

  it('shows the empty state inside the card layout without per-cell labels', () => {
    width = 300;
    const { container } = renderTable({ rows: [], emptyTitle: 'No faculty yet' });
    expect(wrapper(container)).toHaveClass('is-stacked');
    expect(screen.getByText('No faculty yet')).toBeInTheDocument();
    expect(container.querySelector('td.cell-state')).not.toHaveAttribute('data-label');
  });
});
