import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import TimetablesPage from './TimetablesPage.jsx';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const TERM = { id: 1, name: 'Autumn 2026', academic_year: '2026-27' };
const ACTIONS_BY_STATUS = { draft: ['submit'], validated: ['submit'], pending_approval: ['approve', 'reject'], approved: ['reject', 'publish'], published: [], rejected: ['submit'], archived: [] };
const timetable = (status = 'draft', over = {}) => ({
  id: 1, term: TERM, name: 'Autumn 2026 timetable v1', version: 1, status, validation_passed: status !== 'draft' && status !== 'rejected', validated_at: '2026-10-02T09:00:00', generated_at: '2026-10-01T10:00:00',
  periods: 3, unscheduled_sessions: 0, can_discard: ['draft', 'validated', 'rejected'].includes(status), can_edit: ['draft', 'validated', 'rejected'].includes(status),
  allowed_actions: ACTIONS_BY_STATUS[status], is_current_published: status === 'published', approved_by: null, approved_at: null, published_at: null, rejection_reason: null, ...over,
});
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });
const detail = (status, over = {}) => ({ ...timetable(status, over), entries: [], unscheduled: [], workload: [] });
const PASSED = {
  timetable_id: 1, status: 'validated', validation_passed: true, is_valid: true, is_complete: true, validated_at: '2026-10-02T09:00:00',
  counts: { required_sessions: 32, scheduled_sessions: 32, unscheduled_sessions: 0, scheduled_periods: 36, hard_errors: 0, warnings: 0 }, hard_errors: [], warnings: [], unscheduled: [],
};
const FAILED = {
  ...PASSED, status: 'draft', validation_passed: false, is_valid: false,
  counts: { ...PASSED.counts, hard_errors: 1 },
  hard_errors: [{ code: 'room_unavailable', severity: 'hard', message: 'R201 is out of service.', details: {} }],
};
const apiError = (code, message, details = {}) => Object.assign(new Error(message), { code, details });

let current;
beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  current = detail('draft');
  api.get.mockImplementation((url) => {
    if (url.startsWith('/timetables?')) return Promise.resolve(listOf([current]));
    if (url.startsWith('/timetables/')) return Promise.resolve(current);
    if (url.startsWith('/time-slots')) return Promise.resolve({ items: [] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
});

async function openDetail() {
  render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
  await userEvent.click(within(await screen.findByRole('row', { name: /timetable v1/ })).getByRole('button', { name: /View/ }));
  await screen.findByRole('heading', { name: 'Autumn 2026 timetable v1' });
  return screen.getByRole('heading', { name: 'Review and publish' }).closest('section');
}

describe('Review panel - what is offered', () => {
  it.each([
    ['draft', ['Submit for approval']],
    ['validated', ['Submit for approval']],
    ['pending_approval', ['Approve', 'Reject…']],
    ['approved', ['Withdraw approval…', 'Publish']],
    ['rejected', ['Submit for approval']],
  ])('a %s timetable offers %j', async (status, labels) => {
    current = detail(status);
    const panel = await openDetail();
    expect(within(panel).getAllByRole('button').map((b) => b.textContent)).toEqual(expect.arrayContaining(labels));
    expect(within(panel).getAllByRole('button')).toHaveLength(labels.length);
  });

  it('shows the workflow steps with the current one marked', async () => {
    current = detail('pending_approval');
    const panel = await openDetail();
    const steps = within(panel).getByRole('list', { name: 'Timetable workflow' });
    expect(within(steps).getByText('Pending approval')).toHaveAttribute('aria-current', 'step');
    expect(within(steps).getByText('Draft')).not.toHaveAttribute('aria-current');
  });

  it('a published timetable is final: current badge, no actions, no editing', async () => {
    current = detail('published', { published_at: '2026-10-03T09:00:00', can_edit: false, can_discard: false });
    const panel = await openDetail();
    expect(within(panel).getByText('Current published version')).toBeInTheDocument();
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
    expect(within(panel).getByText(/No further action is available for a published timetable/)).toBeInTheDocument();
    expect(screen.getByText(/can no longer be edited/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Discard/ })).not.toBeInTheDocument();
  });

  it('an archived timetable explains that a newer version replaced it', async () => {
    current = detail('archived', { can_edit: false, can_discard: false });
    const panel = await openDetail();
    expect(within(panel).getByText(/newer version has replaced this one/)).toBeInTheDocument();
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
  });

  it('a rejected timetable shows the saved reason', async () => {
    current = detail('rejected', { rejection_reason: 'Move CS301 away from Monday.' });
    const panel = await openDetail();
    expect(within(panel).getByText(/Move CS301 away from Monday\./)).toBeInTheDocument();
  });
});

describe('Review panel - confirmations and success', () => {
  it('asks before submitting, does nothing on cancel, and posts on confirm', async () => {
    api.post.mockResolvedValue({ timetable: timetable('pending_approval'), validation: PASSED, superseded: [] });
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit for approval' }));
    let dialog = await screen.findByRole('dialog', { name: 'Submit this timetable for approval?' });
    expect(within(dialog).getByText(/validated again now/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit for approval' }));
    dialog = await screen.findByRole('dialog', { name: 'Submit this timetable for approval?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Submit' }));
    expect(api.post).toHaveBeenCalledWith('/timetables/1/submit', {});
    expect(await screen.findByText('Submitted for approval', { selector: '*' })).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByRole('button', { name: 'Approve' })).toBeInTheDocument());
    expect(within(panel).queryByRole('button', { name: 'Submit for approval' })).not.toBeInTheDocument();
  });

  it('approving does not publish and says so', async () => {
    current = detail('pending_approval');
    api.post.mockResolvedValue({ timetable: timetable('approved', { approved_at: '2026-10-02T10:00:00' }), validation: PASSED, superseded: [] });
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve this timetable?' });
    expect(within(dialog).getByText(/does not publish it/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve' }));
    expect(api.post).toHaveBeenCalledWith('/timetables/1/approve', {});
    await waitFor(() => expect(within(panel).getByRole('button', { name: 'Publish' })).toBeInTheDocument());
    expect(within(panel).getByText(/Approved .*\./)).toBeInTheDocument();
  });

  it('publishing warns that the current version is archived and reports it afterwards', async () => {
    current = detail('approved');
    api.post.mockResolvedValue({ timetable: timetable('published', { published_at: '2026-10-03T09:00:00', can_edit: false, can_discard: false }), validation: PASSED, superseded: [7] });
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Publish' }));
    const dialog = await screen.findByRole('dialog', { name: 'Publish this timetable?' });
    expect(within(dialog).getByText(/current published version of Autumn 2026/)).toBeInTheDocument();
    expect(within(dialog).getByText(/archived, and its history is kept/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));
    expect(api.post).toHaveBeenCalledWith('/timetables/1/publish', {});
    expect(await screen.findByText('The previous published version was archived.')).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByText('Current published version')).toBeInTheDocument());
    expect(within(panel).queryAllByRole('button')).toHaveLength(0);
  });
});

describe('Review panel - refusals', () => {
  it('shows exactly why validation refused the step and keeps the status', async () => {
    api.post.mockRejectedValue(apiError('validation_failed', 'This timetable cannot be submitted for approval: the latest validation found 1 hard error.', { validation: FAILED }));
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit for approval' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Submit' }));
    expect(await within(panel).findByText(/cannot be submitted for approval/)).toBeInTheDocument();
    expect(await screen.findByText('R201 is out of service.')).toBeInTheDocument();
    expect(screen.getByText(/Validation failed\./)).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('an out-of-date screen is refreshed after an illegal transition', async () => {
    api.post.mockRejectedValue(apiError('illegal_transition', 'A approved timetable cannot be submitted for approval; it must be draft first.', { status: 'approved' }));
    const panel = await openDetail();
    const calls = () => api.get.mock.calls.filter((c) => c[0] === '/timetables/1').length;
    const before = calls();
    current = detail('approved');
    await userEvent.click(within(panel).getByRole('button', { name: 'Submit for approval' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Submit' }));
    expect(await within(panel).findByText(/cannot be submitted for approval/)).toBeInTheDocument();
    await waitFor(() => expect(calls()).toBeGreaterThan(before));
    await waitFor(() => expect(within(panel).getByRole('button', { name: 'Publish' })).toBeInTheDocument());
  });
});

describe('Review panel - rejecting', () => {
  it('needs a reason before anything is sent', async () => {
    current = detail('pending_approval');
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Reject…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Reject this timetable?' });
    await userEvent.type(within(dialog).getByLabelText('Reason'), 'no');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject timetable' }));
    expect(await within(dialog).findByText('Give a reason of at least 5 characters.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('sends the tidied reason and shows the rejected state with the reason', async () => {
    current = detail('pending_approval');
    api.post.mockResolvedValue({ timetable: timetable('rejected', { rejection_reason: 'Friday labs clash.' }), validation: null, superseded: [] });
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Reject…' }));
    const dialog = await screen.findByRole('dialog', { name: 'Reject this timetable?' });
    await userEvent.type(within(dialog).getByLabelText('Reason'), '  Friday   labs clash. ');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject timetable' }));
    expect(api.post).toHaveBeenCalledWith('/timetables/1/reject', { reason: 'Friday labs clash.' });
    expect(await within(panel).findByText(/Friday labs clash\./)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(within(panel).getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
  });

  it('an approved timetable offers to withdraw the approval', async () => {
    current = detail('approved');
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Withdraw approval…' }));
    expect(await screen.findByRole('dialog', { name: 'Withdraw this approval?' })).toBeInTheDocument();
  });

  it('cancelling the rejection sends nothing', async () => {
    current = detail('pending_approval');
    const panel = await openDetail();
    await userEvent.click(within(panel).getByRole('button', { name: 'Reject…' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('Timetable list', () => {
  it('marks the current published version', async () => {
    current = timetable('published');
    render(<MemoryRouter><ToastProvider><TimetablesPage /></ToastProvider></MemoryRouter>);
    const row = await screen.findByRole('row', { name: /timetable v1/ });
    expect(within(row).getByText('Published')).toBeInTheDocument();
    expect(within(row).getByText('Current')).toBeInTheDocument();
  });
});
