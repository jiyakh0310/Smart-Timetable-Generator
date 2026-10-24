import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import WeeklyTimetable from './WeeklyTimetable.jsx';

// Test fixtures only - the real app never ships sample timetable data.
const days = [
  { key: 0, label: 'Mon', name: 'Monday' },
  { key: 1, label: 'Tue', name: 'Tuesday' },
];
const periods = [
  { key: 'p1', start: '09:00', end: '10:00', kind: 'class' },
  { key: 'p2', start: '10:00', end: '11:00', kind: 'class' },
  { key: 'b', start: '11:00', end: '12:00', kind: 'break' },
];
const entries = [
  { id: 1, dayKey: 0, periodKey: 'p1', span: 2, title: 'DS Lab', lines: ['Dr. Sharma', 'Lab 1'], kind: 'lab' },
  { id: 2, dayKey: 1, periodKey: 'p1', title: 'Databases', lines: ['Room 201'], kind: 'theory' },
];

const week = (container) => within(container.querySelector('.tt-week'));
const dayView = (container) => within(container.querySelector('.tt-day'));

describe('WeeklyTimetable', () => {
  it('places entries in the week grid and marks the break row', () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    expect(week(container).getByText('DS Lab')).toBeInTheDocument();
    expect(week(container).getByText('Databases')).toBeInTheDocument();
    expect(week(container).getByText('Break')).toBeInTheDocument();
  });

  it('spans a two-period lab over two rows without rendering the covered cell twice', () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    const labCell = week(container).getByText('DS Lab').closest('td');
    expect(labCell).toHaveAttribute('rowspan', '2');
    expect(week(container).getAllByText('DS Lab')).toHaveLength(1);
  });

  it('identifies lab vs theory with a text label, not only colour', () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    expect(week(container).getByText('Lab')).toBeInTheDocument();
    expect(week(container).getByText('Theory')).toBeInTheDocument();
  });

  it('switches the day list when a day tab is chosen', async () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    await userEvent.click(screen.getByRole('tab', { name: /Tue/ }));
    expect(screen.getByRole('tab', { name: /Tue/ })).toHaveAttribute('aria-selected', 'true');
    expect(dayView(container).getByText('Databases')).toBeInTheDocument();
    expect(dayView(container).queryByText('DS Lab')).not.toBeInTheDocument();
  });

  it('steps through days with previous/next and wraps around', async () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    await userEvent.click(screen.getByRole('tab', { name: /Mon/ }));
    expect(dayView(container).getByRole('heading', { name: 'Monday' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next day' }));
    expect(dayView(container).getByRole('heading', { name: 'Tuesday' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next day' }));
    expect(dayView(container).getByRole('heading', { name: 'Monday' })).toBeInTheDocument();
  });

  it('shows the hint and renders no classes when there are no entries (never invents data)', () => {
    const { container } = render(<WeeklyTimetable days={days} periods={periods} entries={[]} emptyHint="Nothing published yet." />);
    expect(screen.getByText('Nothing published yet.')).toBeInTheDocument();
    expect(container.querySelectorAll('.tt-entry')).toHaveLength(0);
  });

  it('has no editing controls (read-only)', () => {
    render(<WeeklyTimetable days={days} periods={periods} entries={entries} />);
    expect(screen.queryByRole('button', { name: /edit|delete|add|save/i })).not.toBeInTheDocument();
  });
});
