import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import AvailabilityPage from './AvailabilityPage.jsx';

const api = { get: vi.fn(), put: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), put: (...a) => api.put(...a) } }));

const FACULTY = {
  items: [
    { id: 1, employee_code: 'F001', name: 'Dr. Rakesh Sharma', is_active: true },
    { id: 2, employee_code: 'F002', name: 'Dr. Meera Iyer', is_active: true },
    { id: 3, employee_code: 'F300', name: 'Prof. Old Hand', is_active: false },
  ],
  page: 1, per_page: 100, total: 3, pages: 1,
};

// Monday + Tuesday x periods 1-2 (class) and 3 (break); Monday period 4 is a disabled class slot that already holds a saved preference.
const slot = (id, day, period, over = {}) => ({
  time_slot_id: id, day_of_week: day, day_name: ['Monday', 'Tuesday'][day], period_no: period, start_time: `${String(8 + period).padStart(2, '0')}:00`, end_time: `${String(9 + period).padStart(2, '0')}:00`,
  slot_type: 'class', is_active: true, status: 'available', ...over,
});
const availability = (over = {}, facultyOver = {}) => ({
  faculty: { id: 1, name: 'Dr. Rakesh Sharma', employee_code: 'F001', is_active: true, ...facultyOver },
  slots: [
    slot(1, 0, 1), slot(2, 0, 2, { status: 'unavailable' }), slot(3, 0, 3, { slot_type: 'break' }), slot(4, 0, 4, { is_active: false, status: 'preferred' }),
    slot(5, 1, 1), slot(6, 1, 2), slot(7, 1, 3, { slot_type: 'break' }), slot(8, 1, 4),
  ],
  summary: { unavailable: 1, preferred: 1 },
  ...over,
});

let current;
const renderPage = (url = '/admin/availability?faculty=1') =>
  render(<MemoryRouter initialEntries={[url]}><ToastProvider><AvailabilityPage /></ToastProvider></MemoryRouter>);
const cell = (name) => screen.getByRole('button', { name });
const loaded = () => screen.findByRole('table', { name: /Weekly availability for/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  current = availability();
  api.get.mockImplementation((path) => Promise.resolve(path.startsWith('/faculty?') ? FACULTY : path === '/faculty/2/availability' ? availability({}, { id: 2, name: 'Dr. Meera Iyer', employee_code: 'F002' }) : current));
});

describe('Availability screen - viewing', () => {
  it('opens the faculty member from the link, draws the weekly grid and explains hard vs soft', async () => {
    renderPage();
    await loaded();
    expect(screen.getByRole('heading', { level: 1, name: 'Faculty availability' })).toBeInTheDocument();
    expect(screen.getByLabelText('Faculty member')).toHaveValue('1');
    expect(screen.getByText('Dr. Rakesh Sharma · F001')).toBeInTheDocument();
    const legend = screen.getByRole('list', { name: 'What each status means' });
    expect(legend).toHaveTextContent('Hard rule. They will never be scheduled');
    expect(legend).toHaveTextContent('Soft wish. Used when possible, never required');
    expect(screen.getByRole('columnheader', { name: 'Monday' })).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: /Period 1/ })).toBeInTheDocument();
  });

  it('shows saved statuses in words (not only colour), and counts them', async () => {
    renderPage();
    await loaded();
    expect(cell('Monday period 2, 10:00 to 11:00: Unavailable. Activate to change.')).toHaveTextContent('Unavailable');
    expect(cell(/Monday period 1,.*: Available/)).toHaveTextContent('Available');
    expect(screen.getByText('1 unavailable')).toBeInTheDocument();
    expect(screen.getByText('0 preferred')).toBeInTheDocument(); // the disabled slot's saved preference is not counted as editable
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  it('breaks and disabled slots are not interactive, and a disabled slot says its saved value is kept', async () => {
    renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /period 3/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Monday period 4/ })).not.toBeInTheDocument();
    expect(screen.getAllByText('Break')).toHaveLength(2);
    expect(screen.getByText('Disabled')).toBeInTheDocument();
    expect(screen.getByText('Preferred kept')).toBeInTheDocument();
  });

  it('Save is disabled until something changes', async () => {
    renderPage();
    await loaded();
    expect(screen.getByRole('button', { name: /Save availability/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard changes' })).toBeDisabled();
  });

  it('prompts to choose someone when none is selected, and offers inactive faculty too', async () => {
    renderPage('/admin/availability');
    expect(await screen.findByRole('heading', { name: 'Choose a faculty member' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'F300 · Prof. Old Hand (inactive)' })).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('/availability'));
  });

  it('shows an empty state when there are no faculty yet', async () => {
    api.get.mockImplementation(() => Promise.resolve({ items: [], page: 1, per_page: 100, total: 0, pages: 1 }));
    renderPage('/admin/availability');
    expect(await screen.findByRole('heading', { name: 'No faculty members yet' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Faculty' })).toHaveAttribute('href', '/admin/faculty');
  });

  it('shows a load error with Try again', async () => {
    api.get.mockImplementation((path) => (path.includes('/availability') ? Promise.reject(new Error('Faculty member not found.')) : Promise.resolve(FACULTY)));
    renderPage();
    expect(await screen.findByText('Faculty member not found.')).toBeInTheDocument();
    api.get.mockImplementation((path) => Promise.resolve(path.startsWith('/faculty?') ? FACULTY : current));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await loaded()).toBeInTheDocument();
  });

  it('notes when the faculty member is inactive but still allows editing', async () => {
    current = availability({}, { is_active: false });
    renderPage();
    await loaded();
    expect(screen.getByText(/This faculty member is inactive. Availability can still be edited/)).toBeInTheDocument();
    expect(cell(/Monday period 1,/)).toBeEnabled();
  });

  it('explains when there are no usable time slots', async () => {
    current = availability({ slots: [slot(3, 0, 3, { slot_type: 'break' }), slot(4, 0, 4, { is_active: false })] });
    renderPage();
    expect(await screen.findByRole('heading', { name: 'No usable time slots' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Time Slots' })).toHaveAttribute('href', '/admin/time-slots');
  });
});

describe('Availability screen - editing (ISH-TC09..TC11)', () => {
  it('each press cycles available -> unavailable -> preferred -> available and flags unsaved changes', async () => {
    renderPage();
    await loaded();
    const target = () => screen.getByRole('button', { name: /Tuesday period 1,/ });
    expect(target()).toHaveTextContent('Available');
    await userEvent.click(target());
    expect(target()).toHaveTextContent('Unavailable');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(screen.getByText('2 unavailable')).toBeInTheDocument();
    await userEvent.click(target());
    expect(target()).toHaveTextContent('Preferred');
    expect(screen.getByText('1 preferred')).toBeInTheDocument();
    await userEvent.click(target());
    expect(target()).toHaveTextContent('Available');
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
  });

  it('is operable from the keyboard', async () => {
    renderPage();
    await loaded();
    const target = screen.getByRole('button', { name: /Tuesday period 2,/ });
    target.focus();
    await userEvent.keyboard('{Enter}');
    expect(target).toHaveTextContent('Unavailable');
    await userEvent.keyboard(' ');
    expect(target).toHaveTextContent('Preferred');
  });

  it('saves only the non-default settings of editable slots, then shows a toast and clears the unsaved flag', async () => {
    api.put.mockResolvedValue({ ...current, slots: current.slots.map((s) => (s.time_slot_id === 5 ? { ...s, status: 'preferred' } : s)), summary: { unavailable: 1, preferred: 1 } });
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ })); // -> preferred
    await userEvent.click(screen.getByRole('button', { name: /Save availability/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/faculty/1/availability', {
      entries: [{ time_slot_id: 2, status: 'unavailable' }, { time_slot_id: 5, status: 'preferred' }],
    }));
    expect(await screen.findByText('Availability saved')).toBeInTheDocument();
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save availability/ })).toBeDisabled();
  });

  it('never sends the disabled slot or breaks, even though the disabled one holds a saved preference', async () => {
    api.put.mockResolvedValue(current);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.click(screen.getByRole('button', { name: /Save availability/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const ids = api.put.mock.calls[0][1].entries.map((e) => e.time_slot_id);
    expect(ids).not.toContain(4);
    expect(ids).not.toContain(3);
    expect(ids).not.toContain(7);
  });

  it('Discard changes restores the saved settings', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
    expect(screen.getByRole('button', { name: /Tuesday period 1,/ })).toHaveTextContent('Available');
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });

  it('"Set everything to available" clears editable cells but leaves the disabled slot alone', async () => {
    api.put.mockResolvedValue({ ...current, slots: current.slots.map((s) => ({ ...s, status: s.time_slot_id === 4 ? 'preferred' : 'available' })), summary: { unavailable: 0, preferred: 0 } });
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Set everything to available' }));
    expect(screen.getByRole('button', { name: /Monday period 2,/ })).toHaveTextContent('Available');
    expect(screen.getByText('Preferred kept')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Save availability/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/faculty/1/availability', { entries: [] }));
  });

  it('shows the server message and keeps the unsaved changes when saving fails', async () => {
    api.put.mockRejectedValue(Object.assign(new Error('Some time slots cannot be used.'), { details: { 'entries.0': 'Monday period 4 is disabled and cannot be configured.' } }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.click(screen.getByRole('button', { name: /Save availability/ }));
    expect(await screen.findByText(/Some time slots cannot be used\. Monday period 4 is disabled/)).toBeInTheDocument();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save availability/ })).toBeEnabled();
  });
});

describe('Availability screen - switching faculty', () => {
  it('switches straight away when nothing is unsaved', async () => {
    renderPage();
    await loaded();
    await userEvent.selectOptions(screen.getByLabelText('Faculty member'), '2');
    expect(await screen.findByText('Dr. Meera Iyer · F002')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/faculty/2/availability');
  });

  it('asks before discarding unsaved changes; Cancel keeps editing the same person', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.selectOptions(screen.getByLabelText('Faculty member'), '2');
    const dialog = screen.getByRole('dialog', { name: 'Discard unsaved changes?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByText('Dr. Rakesh Sharma · F001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Tuesday period 1,/ })).toHaveTextContent('Unavailable');
    expect(api.get).not.toHaveBeenCalledWith('/faculty/2/availability');
  });

  it('Discard and switch loads the other faculty member', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Tuesday period 1,/ }));
    await userEvent.selectOptions(screen.getByLabelText('Faculty member'), '2');
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Discard and switch' }));
    expect(await screen.findByText('Dr. Meera Iyer · F002')).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });
});
