import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import TimeSlotsPage from './TimeSlotsPage.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const slot = (over = {}) => ({
  id: 1, day_of_week: 0, day_name: 'Monday', period_no: 1, start_time: '09:00', end_time: '10:00',
  slot_type: 'class', is_active: true, in_use: false, usage: { timetable_entries: 0, faculty_availability: 0 }, ...over,
});
const listOf = (items, extra = {}) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1, ...extra });
const SLOTS = [
  slot(),
  slot({ id: 2, period_no: 2, start_time: '10:00', end_time: '11:00' }),
  slot({ id: 3, period_no: 4, start_time: '12:00', end_time: '13:00', slot_type: 'break' }),
  slot({ id: 4, day_of_week: 1, day_name: 'Tuesday', period_no: 1, in_use: true, usage: { timetable_entries: 3, faculty_availability: 0 } }),
];

const renderPage = () => render(<MemoryRouter><ToastProvider><TimeSlotsPage /></ToastProvider></MemoryRouter>);
const calls = (fn) => fn.mock.calls.map((c) => c[0]);
const lastGet = () => calls(api.get)[calls(api.get).length - 1];
// Wait until the table rows (not the day <option>s in the filter) are on screen.
const loaded = () => screen.findByRole('row', { name: /Tuesday Period 1/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockResolvedValue(listOf(SLOTS));
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getByRole('button', { name: /Add time slots/ }));
  return screen.getByRole('dialog', { name: 'Add time slots' });
}
const setTime = (dialog, label, value) => fireEvent.change(within(dialog).getByLabelText(label), { target: { value } });

describe('Time slots screen - listing', () => {
  it('shows real rows from the API with type, status and in-use badges', async () => {
    renderPage();
    await loaded();
    const table = screen.getByRole('table', { name: 'Time slots' });
    expect(within(table).getAllByText('Monday')).toHaveLength(3);
    expect(within(screen.getByRole('row', { name: /Monday Period 4/ })).getByText('Break')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /Tuesday Period 1/ })).getByText('In use')).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-4 of 4 time slots');
    expect(lastGet()).toBe('/time-slots?page=1&per_page=10');
  });

  it('is titled and has a single h1', async () => {
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: 'Time slots' })).toBeInTheDocument();
    await loaded();
  });

  it('sends the chosen filters to the server', async () => {
    renderPage();
    await loaded();
    await userEvent.selectOptions(screen.getByLabelText('Day'), 'Wednesday');
    await waitFor(() => expect(lastGet()).toContain('day=2'));
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'Break');
    await waitFor(() => expect(lastGet()).toContain('slot_type=break'));
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Disabled');
    await waitFor(() => expect(lastGet()).toContain('active=false'));
  });

  it('sends the search text after a pause, and Clear removes it', async () => {
    renderPage();
    await loaded();
    await userEvent.type(screen.getByRole('searchbox', { name: /Search time slots/ }), '09:');
    await waitFor(() => expect(lastGet()).toContain('q=09%3A'));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(lastGet()).not.toContain('q='));
  });

  it('shows an empty state with an Add button when there are no slots', async () => {
    api.get.mockResolvedValue(listOf([]));
    renderPage();
    expect(await screen.findByRole('heading', { name: 'No time slots yet' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Add time slots/ }).length).toBeGreaterThanOrEqual(1);
  });

  it('shows the error and recovers when Try again succeeds', async () => {
    api.get.mockRejectedValueOnce(new Error('Cannot reach the server. Is the backend running?'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await loaded();
    expect(within(screen.getByRole('table', { name: 'Time slots' })).getAllByText('Monday')).toHaveLength(3);
  });
});

describe('Time slots screen - create (DIY-TC09, TC10, TC12)', () => {
  it('opens with focus on the first field and Mon-Fri preselected', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByRole('checkbox', { name: 'Mon' })).toHaveFocus();
    expect(within(dialog).getByRole('checkbox', { name: 'Fri' })).toBeChecked();
    expect(within(dialog).getByRole('checkbox', { name: 'Sat' })).not.toBeChecked();
  });

  it('blocks an empty form, lists every problem and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));
    expect(await within(dialog).findByText('Enter a whole number from 1 to 20.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a start time.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose an end time.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('requires at least one day', async () => {
    renderPage();
    const dialog = await openCreate();
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']) await userEvent.click(within(dialog).getByRole('checkbox', { name: day }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));
    expect(await within(dialog).findByText('Select at least one day.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('DIY-TC10: rejects an end time before the start time without calling the API', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Period number'), '1');
    setTime(dialog, 'Start time', '11:00');
    setTime(dialog, 'End time', '10:00');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));
    expect(await within(dialog).findByText('End time must be after the start time.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('DIY-TC09 / TC12: sends the days, period and times, shows a success toast, closes and refreshes the list', async () => {
    api.post.mockResolvedValue({ items: [slot(), slot({ id: 9 })] });
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Period number'), '1');
    setTime(dialog, 'Start time', '09:00');
    setTime(dialog, 'End time', '10:00');
    const getsBefore = api.get.mock.calls.length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/time-slots', {
      days: [0, 1, 2, 3, 4], period_no: 1, start_time: '09:00', end_time: '10:00', slot_type: 'class', is_active: true,
    }));
    expect(await screen.findByText('2 time slots created')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(api.get.mock.calls.length).toBeGreaterThan(getsBefore);
  });

  it('shows the server conflict message on the form, keeps the dialog open and the data entered', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('Monday 09:30-10:30 overlaps Period 1 (09:00-10:00).'), {
      details: { start_time: 'Overlaps Period 1 on Monday.', end_time: 'Overlaps Period 1 on Monday.' },
    }));
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Period number'), '9');
    setTime(dialog, 'Start time', '09:30');
    setTime(dialog, 'End time', '10:30');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }));
    expect((await within(dialog).findAllByRole('alert')).length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getByText('Monday 09:30-10:30 overlaps Period 1 (09:00-10:00).')).toBeInTheDocument(); // form-level message
    expect(within(dialog).getAllByText('Overlaps Period 1 on Monday.')).toHaveLength(2); // start + end fields
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Period number')).toHaveValue(9);
    expect(within(dialog).getByRole('button', { name: 'Create' })).toBeEnabled();
  });

  it('Escape cancels without saving', async () => {
    renderPage();
    await openCreate();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('Time slots screen - edit (DIY-TC11)', () => {
  it('prefills the form from the row and sends only valid changes', async () => {
    api.patch.mockResolvedValue(slot({ end_time: '10:30' }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit Monday, Period 1 (09:00-10:00)' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit Monday · Period 1' });
    expect(within(dialog).getByLabelText('Start time')).toHaveValue('09:00');
    expect(within(dialog).getByLabelText('Day')).toHaveValue('0');
    setTime(dialog, 'End time', '10:30');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/time-slots/1', {
      day_of_week: 0, period_no: 1, start_time: '09:00', end_time: '10:30', slot_type: 'class', is_active: true,
    }));
    expect(await screen.findByText('Time slot updated')).toBeInTheDocument();
  });

  it('locks day, period and times when a timetable already uses the slot', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Edit Tuesday, Period 1/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByLabelText('Start time')).toBeDisabled();
    expect(within(dialog).getByLabelText('Period number')).toBeDisabled();
    expect(within(dialog).getByLabelText('Type')).toBeEnabled();
    expect(within(dialog).getByText(/locked because a timetable uses this slot/)).toBeInTheDocument();
  });
});

describe('Time slots screen - delete', () => {
  it('asks first; Cancel leaves everything untouched', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Delete Monday, Period 2/ }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this time slot?' });
    expect(dialog).toHaveTextContent('permanently removed');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('deletes an unused slot after confirmation, then shows a toast and refreshes', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Delete Monday, Period 2/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/time-slots/2'));
    expect(await screen.findByText('Time slot deleted')).toBeInTheDocument();
  });

  it('explains that an in-use slot cannot be deleted and offers to disable it instead (nothing is deleted)', async () => {
    api.patch.mockResolvedValue(slot({ id: 4, is_active: false }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Delete Tuesday, Period 1/ }));
    const dialog = screen.getByRole('dialog', { name: 'This time slot is in use' });
    expect(dialog).toHaveTextContent('3 timetable entries');
    expect(dialog).toHaveTextContent('Disable it instead');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Disable slot' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/time-slots/4', { is_active: false }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(await screen.findByText('Time slot disabled')).toBeInTheDocument();
  });

  it('shows the server message in an error toast if the delete is refused', async () => {
    api.delete.mockRejectedValue(new Error('This time slot is in use (1 timetable entry) and cannot be deleted.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: /Delete Monday, Period 1/ }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not complete the action')).toBeInTheDocument();
    expect(screen.getByText(/cannot be deleted/)).toBeInTheDocument();
  });
});
