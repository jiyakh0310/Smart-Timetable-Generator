// Tests for the redesign-only behaviour: show/hide password, the phone availability grid, publish styling, timetable header, media-query hook.
import { act, render, renderHook, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfirmDialog, PasswordField, ToastProvider } from './components/ui';
import useMediaQuery from './hooks/useMediaQuery.js';
import AvailabilityPage from './features/isha/AvailabilityPage.jsx';
import LoginForm from './features/isha/LoginForm.jsx';
import ReviewPanel from './features/jiya/ReviewPanel.jsx';
import TimetablesPage from './features/jiya/TimetablesPage.jsx';

const api = { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn(), download: vi.fn() };
vi.mock('./services/api.js', () => ({ api: { get: (...a) => api.get(...a), put: (...a) => api.put(...a), post: (...a) => api.post(...a), delete: (...a) => api.delete(...a), patch: (...a) => api.patch(...a), download: (...a) => api.download(...a) } }));
vi.mock('./app/AuthContext.jsx', () => ({ useAuth: () => ({ login: vi.fn() }) }));

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); });
afterEach(() => { delete window.matchMedia; });

describe('PasswordField', () => {
  it('hides the value by default and the toggle reveals and hides it again', async () => {
    render(<PasswordField label="Password" value="s3cret" onChange={() => {}} />);
    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    const toggle = screen.getByRole('button', { name: 'Show password' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(toggle);
    expect(input).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });

  it('shows an error with the field and never submits the surrounding form when toggled', async () => {
    const submit = vi.fn((e) => e.preventDefault());
    render(<form onSubmit={submit}><PasswordField label="Password" value="" onChange={() => {}} error="Enter your password." /></form>);
    expect(screen.getByLabelText('Password')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your password.');
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(submit).not.toHaveBeenCalled();
  });

  it('is part of the sign-in form and keeps the value typed', async () => {
    render(<MemoryRouter><LoginForm /></MemoryRouter>);
    await userEvent.type(screen.getByLabelText('Password'), 'abc123');
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(screen.getByLabelText('Password')).toHaveValue('abc123');
    expect(screen.getByLabelText('Email')).toHaveAttribute('placeholder', 'you@institution.edu');
  });
});

describe('useMediaQuery', () => {
  it('falls back where matchMedia does not exist', () => {
    expect(renderHook(() => useMediaQuery('(min-width: 1px)', true)).result.current).toBe(true);
    expect(renderHook(() => useMediaQuery('(min-width: 1px)', false)).result.current).toBe(false);
  });

  it('follows the browser and stops listening on unmount', () => {
    const listeners = new Set();
    const state = { matches: false };
    window.matchMedia = vi.fn(() => ({ get matches() { return state.matches; }, addEventListener: (_, f) => listeners.add(f), removeEventListener: (_, f) => listeners.delete(f) }));
    const { result, unmount } = renderHook(() => useMediaQuery('(max-width: 760px)', true));
    expect(result.current).toBe(false);
    act(() => { state.matches = true; listeners.forEach((f) => f()); });
    expect(result.current).toBe(true);
    unmount();
    expect(listeners.size).toBe(0);
  });
});

describe('Availability grid on a phone', () => {
  const slot = (id, day, period, over = {}) => ({
    time_slot_id: id, day_of_week: day, day_name: ['Monday', 'Tuesday'][day], period_no: period, start_time: `${8 + period}:00`, end_time: `${9 + period}:00`, slot_type: 'class', is_active: true, status: 'available', ...over,
  });
  const data = { faculty: { id: 1, name: 'Dr. Rakesh Sharma', employee_code: 'F001', is_active: true }, slots: [slot(1, 0, 1), slot(2, 0, 2), slot(3, 1, 1), slot(4, 1, 2)], summary: { unavailable: 0, preferred: 0 } };
  const FACULTY = { items: [{ id: 1, employee_code: 'F001', name: 'Dr. Rakesh Sharma', is_active: true }], page: 1, per_page: 100, total: 1, pages: 1 };
  const mount = () => {
    api.get.mockImplementation((p) => Promise.resolve(p.startsWith('/faculty?') ? FACULTY : data));
    return render(<MemoryRouter initialEntries={['/admin/availability?faculty=1']}><ToastProvider><AvailabilityPage /></ToastProvider></MemoryRouter>);
  };

  it('on a wide screen there are no day tabs and every day is a column', async () => {
    mount();
    await screen.findByRole('table', { name: /Weekly availability/ });
    expect(screen.queryByRole('tablist', { name: 'Day of week' })).not.toBeInTheDocument();
    expect(screen.getByRole('table', { name: /Weekly availability/ })).not.toHaveClass('is-one-day');
  });

  it('on a phone it offers day tabs and marks only the chosen day as shown', async () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    const { container } = mount();
    const table = await screen.findByRole('table', { name: /Weekly availability/ });
    expect(table).toHaveClass('is-one-day');
    const tabs = screen.getByRole('tablist', { name: 'Day of week' });
    expect(within(tabs).getByRole('tab', { name: 'Mon' })).toHaveAttribute('aria-selected', 'true');
    expect(container.querySelectorAll('td[data-picked]')).toHaveLength(2);        // Monday's two periods
    expect(container.querySelector('th.is-picked')).toHaveTextContent('Monday');
    await userEvent.click(within(tabs).getByRole('tab', { name: 'Tue' }));
    expect(within(tabs).getByRole('tab', { name: 'Tue' })).toHaveAttribute('aria-selected', 'true');
    expect(container.querySelector('th.is-picked')).toHaveTextContent('Tuesday');
    expect(container.querySelectorAll('td[data-picked]')).toHaveLength(2);
  });

  it('a change made on one day is kept when switching to another day', async () => {
    window.matchMedia = vi.fn(() => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    mount();
    await screen.findByRole('table', { name: /Weekly availability/ });
    await userEvent.click(screen.getByRole('button', { name: /Monday period 1.*Available/ }));
    expect(screen.getByRole('button', { name: /Monday period 1.*Unavailable/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Tue' }));
    await userEvent.click(screen.getByRole('tab', { name: 'Mon' }));
    expect(screen.getByRole('button', { name: /Monday period 1.*Unavailable/ })).toBeInTheDocument();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
  });
});

describe('Publishing and destructive styling', () => {
  const approved = { id: 1, term: { name: 'Autumn 2026' }, name: 'T v1', status: 'approved', allowed_actions: ['reject', 'publish'], is_current_published: false, approved_at: null, published_at: null, rejection_reason: null };
  const wrap = (ui) => <MemoryRouter><ToastProvider>{ui}</ToastProvider></MemoryRouter>;

  it('Publish is the distinct success action and Reject is the only destructive one', () => {
    render(wrap(<ReviewPanel timetable={approved} onDone={() => {}} onFailedValidation={() => {}} onRefresh={() => {}} />));
    expect(screen.getByRole('button', { name: 'Publish' })).toHaveClass('btn-success');
    const reject = screen.getByRole('button', { name: /Withdraw approval/ });
    expect(reject).toHaveClass('btn-danger-text');
    expect(reject).not.toHaveClass('btn-primary');
  });

  it('the publish confirmation uses the success button, the rejection dialog the danger button', async () => {
    render(wrap(<ReviewPanel timetable={approved} onDone={() => {}} onFailedValidation={() => {}} onRefresh={() => {}} />));
    await userEvent.click(screen.getByRole('button', { name: 'Publish' }));
    const dialog = await screen.findByRole('dialog', { name: 'Publish this timetable?' });
    expect(within(dialog).getByRole('button', { name: 'Publish' })).toHaveClass('btn-success');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await userEvent.click(screen.getByRole('button', { name: /Withdraw approval/ }));
    expect(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reject timetable' })).toHaveClass('btn-danger');
  });

  it('ConfirmDialog tones map to primary, danger and success buttons', () => {
    const { rerender } = render(<ConfirmDialog open title="x" message="m" confirmLabel="Go" tone="danger" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass('btn-danger');
    rerender(<ConfirmDialog open title="x" message="m" confirmLabel="Go" tone="success" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass('btn-success');
    rerender(<ConfirmDialog open title="x" message="m" confirmLabel="Go" onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass('btn-primary');
  });
});

describe('Timetable header', () => {
  const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
  const t = (over = {}) => ({ id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status: 'draft', validation_passed: false, validated_at: null, generated_at: '2026-10-01T10:00:00', periods: 4, unscheduled_sessions: 0, can_discard: true, can_edit: true, allowed_actions: [], is_current_published: false, ...over });
  async function open(over) {
    const row = t(over);
    api.get.mockImplementation((url) => {
      if (url.startsWith('/timetables?')) return Promise.resolve({ items: [row], page: 1, per_page: 10, total: 1, pages: 1 });
      if (url.startsWith('/timetables/')) return Promise.resolve({ ...row, entries: [], unscheduled: [], workload: [] });
      return Promise.resolve({ items: [] });
    });
    render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
    await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
    return screen.findByRole('region', { name: 'Timetable summary' });
  }

  it('shows status, validation state and, for the live version, a "Current published version" badge', async () => {
    const head = await open({ status: 'published', can_edit: false, can_discard: false, is_current_published: true, validation_passed: true, validated_at: 'x' });
    expect(within(head).getByText('Published')).toBeInTheDocument();
    expect(within(head).getByText('Current published version')).toBeInTheDocument();
    expect(within(head).getByText('Validation passed')).toBeInTheDocument();
  });

  it('offers Validate and Discard only where they are allowed', async () => {
    const head = await open({ status: 'approved', can_edit: false, can_discard: false });
    expect(within(head).queryByRole('button', { name: /Validate/ })).not.toBeInTheDocument();
    expect(within(head).queryByRole('button', { name: /Discard/ })).not.toBeInTheDocument();
    expect(within(head).getByRole('button', { name: 'Export PDF' })).toBeInTheDocument();
  });

  it('a draft shows Validate and Discard draft, and no "current" badge', async () => {
    const head = await open({});
    expect(within(head).getByRole('button', { name: /Validate/ })).toBeInTheDocument();
    expect(within(head).getByRole('button', { name: /Discard draft/ })).toBeInTheDocument();
    expect(within(head).queryByText('Current published version')).not.toBeInTheDocument();
  });
});
