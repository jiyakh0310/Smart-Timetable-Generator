import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import AnnouncementsPage from './AnnouncementsPage.jsx';
import { excerpt, formatDate, toPayload, validateAnnouncement } from './announcements.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const item = (over = {}) => ({
  id: 1, title: 'Mid-term exam schedule', message: 'The mid-term exams start on Monday.\n\nPlease check the timetable.', category: 'exam', category_label: 'Exam', status: 'published',
  published_at: '2026-11-10T09:00:00', created_at: '2026-11-09T09:00:00', updated_at: '2026-11-10T09:00:00', author: { name: 'Dr. Anita Verma' }, ...over,
});
const ROWS = [
  item(),
  item({ id: 2, title: 'Room change for CS301', message: 'CS301 moves to R202 from Friday.', category: 'timetable_change', status: 'draft', published_at: null }),
  item({ id: 3, title: 'Water supply interruption', message: 'No water on Saturday.', category: 'urgent' }),
];
const listOf = (items, over = {}) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1, ...over });

const renderPage = () => render(<MemoryRouter><ToastProvider><AnnouncementsPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/announcements')).at(-1);
const loaded = () => screen.findByRole('row', { name: /Water supply/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockResolvedValue(listOf(ROWS));
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getAllByRole('button', { name: /New announcement/ })[0]);
  return screen.getByRole('dialog', { name: 'New announcement' });
}

describe('Announcements (admin) - listing', () => {
  it('shows title, a content snippet, category, status, publish date and author', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /Mid-term exam/ });
    expect(within(row).getByText('Mid-term exam schedule')).toBeInTheDocument();
    expect(within(row).getByText(/The mid-term exams start on Monday/)).toBeInTheDocument();
    expect(within(row).getByText('Exam')).toBeInTheDocument();
    expect(within(row).getByText('Published')).toBeInTheDocument();
    expect(within(row).getByText(formatDate('2026-11-10T09:00:00'))).toBeInTheDocument();
    expect(within(row).getByText('Dr. Anita Verma')).toBeInTheDocument();
    const draft = screen.getByRole('row', { name: /Room change/ });
    expect(within(draft).getByText('Draft')).toBeInTheDocument();
    expect(within(draft).getByText('Timetable change')).toBeInTheDocument();
    expect(within(draft).getByText('—')).toBeInTheDocument();       // no publish date yet
  });

  it('asks the server for the first page and re-asks with the chosen filters', async () => {
    renderPage();
    await loaded();
    expect(gets()[0]).toBe('/announcements?page=1&per_page=10');
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'urgent');
    await waitFor(() => expect(lastList()).toContain('category=urgent'));
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'draft');
    await waitFor(() => expect(lastList()).toContain('status=draft'));
    expect(lastList()).toContain('category=urgent');
  });

  it('searches title and content on the server and can clear the filters', async () => {
    renderPage();
    await loaded();
    await userEvent.type(screen.getByLabelText(/Search announcements/), 'water');
    await waitFor(() => expect(lastList()).toContain('q=water'));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(lastList()).not.toContain('q=water'));
  });

  it('shows the friendly empty state with a way to start', async () => {
    api.get.mockResolvedValue(listOf([]));
    renderPage();
    expect(await screen.findByText('No announcements yet')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /New announcement/ })).toHaveLength(2);
  });

  it('shows "no results" instead of the empty state when filters match nothing', async () => {
    renderPage();
    await loaded();
    api.get.mockResolvedValue(listOf([]));
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'academic');
    expect(await screen.findByText('No results match your search')).toBeInTheDocument();
  });

  it('shows an error with a retry that works', async () => {
    api.get.mockRejectedValueOnce(new Error('Server unavailable'));
    renderPage();
    expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
    api.get.mockResolvedValue(listOf(ROWS));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await loaded()).toBeInTheDocument();
  });

  it('shows pagination information', async () => {
    api.get.mockResolvedValue(listOf(ROWS, { total: 23, pages: 3 }));
    renderPage();
    await loaded();
    expect(document.body.textContent).toMatch(/of 23 announcements/);
  });
});

describe('Announcements (admin) - view', () => {
  it('opens the full text with category, status, publish date and author, and can go on to edit', async () => {
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /Mid-term exam/ })).getByRole('button', { name: 'View Mid-term exam schedule' }));
    const dialog = screen.getByRole('dialog', { name: 'Mid-term exam schedule' });
    expect(within(dialog).getByText(/Please check the timetable/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Published .* · by Dr\. Anita Verma/)).toBeInTheDocument();
    expect(within(dialog).getByText('Exam')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: /Edit/ }));
    expect(await screen.findByRole('dialog', { name: 'Edit announcement' })).toBeInTheDocument();
  });

  it('a draft says it has not been published yet', async () => {
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /Room change/ })).getByRole('button', { name: /View Room change/ }));
    expect(screen.getByText(/Not published yet · by Dr\. Anita Verma/)).toBeInTheDocument();
  });
});

describe('Announcements (admin) - create', () => {
  it('has labelled fields, all five categories and clear choices', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByLabelText('Title')).toHaveFocus();
    expect(within(dialog).getAllByRole('option').map((o) => o.textContent)).toEqual(['General', 'Academic', 'Timetable change', 'Exam', 'Urgent']);
    expect(within(dialog).getByRole('button', { name: 'Save as draft' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Publish now' })).toBeInTheDocument();
  });

  it('refuses an empty form without calling the API and names both fields', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save as draft' }));
    expect(within(dialog).getByText('Enter a title.')).toBeInTheDocument();
    expect(within(dialog).getByText('Write the announcement.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('refuses a title or text that is too short or too long', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Title'), 'ab');
    await userEvent.type(within(dialog).getByLabelText('Announcement'), 'abcd');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish now' }));
    expect(within(dialog).getByText('Use 3 to 200 characters.')).toBeInTheDocument();
    expect(within(dialog).getByText('Use 5 to 5000 characters.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  async function fill(dialog, { title = 'Library timings', message = 'The library is open until 8 pm.', category = 'academic' } = {}) {
    await userEvent.type(within(dialog).getByLabelText('Title'), title);
    await userEvent.selectOptions(within(dialog).getByLabelText('Category'), category);
    await userEvent.type(within(dialog).getByLabelText('Announcement'), message);
  }

  it('saves as a draft', async () => {
    api.post.mockResolvedValue(item({ id: 9, title: 'Library timings', status: 'draft', published_at: null }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save as draft' }));
    expect(api.post).toHaveBeenCalledWith('/announcements', { title: 'Library timings', message: 'The library is open until 8 pm.', category: 'academic', publish: false });
    expect(await screen.findByText('Draft saved')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(() => expect(gets().filter((u) => u.startsWith('/announcements')).length).toBeGreaterThan(1)); // the list reloads
  });

  it('publishes straight away', async () => {
    api.post.mockResolvedValue(item({ id: 9, title: 'Library timings' }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog, { category: 'urgent' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish now' }));
    expect(api.post).toHaveBeenCalledWith('/announcements', expect.objectContaining({ category: 'urgent', publish: true }));
    expect(await screen.findByText('Announcement published')).toBeInTheDocument();
  });

  it('shows the server message and field errors and keeps what was typed', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('Please correct the highlighted fields.'), { details: { title: 'The title must be 3 to 200 characters.' } }));
    renderPage();
    const dialog = await openCreate();
    await fill(dialog);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save as draft' }));
    expect(await within(dialog).findByText('Please correct the highlighted fields.')).toBeInTheDocument();
    expect(within(dialog).getByText('The title must be 3 to 200 characters.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Title')).toHaveValue('Library timings');
    expect(within(dialog).getByRole('button', { name: 'Save as draft' })).toBeEnabled();
  });

  it('cancel closes without saving', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('Escape closes the dialog', async () => {
    renderPage();
    await openCreate();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('Announcements (admin) - edit', () => {
  it('prefills the form, sends only title, text and category, and tells the admin readers see edits at once', async () => {
    api.patch.mockResolvedValue(item({ title: 'Exam schedule moved' }));
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /Mid-term exam/ })).getByRole('button', { name: 'Edit Mid-term exam schedule' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit announcement' });
    expect(within(dialog).getByLabelText('Title')).toHaveValue('Mid-term exam schedule');
    expect(within(dialog).getByLabelText('Category')).toHaveValue('exam');
    expect(within(dialog).getByLabelText('Announcement')).toHaveValue('The mid-term exams start on Monday.\n\nPlease check the timetable.');
    expect(within(dialog).getByText(/visible to faculty and students straight away/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Publish now' })).not.toBeInTheDocument();
    await userEvent.clear(within(dialog).getByLabelText('Title'));
    await userEvent.type(within(dialog).getByLabelText('Title'), 'Exam schedule moved');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    expect(api.patch).toHaveBeenCalledWith('/announcements/1', { title: 'Exam schedule moved', message: 'The mid-term exams start on Monday.\n\nPlease check the timetable.', category: 'exam' });
    expect(await screen.findByText('Announcement updated')).toBeInTheDocument();
  });

  it('a draft has no "visible immediately" warning', async () => {
    renderPage();
    await userEvent.click(within(await screen.findByRole('row', { name: /Room change/ })).getByRole('button', { name: /Edit Room change/ }));
    expect(screen.queryByText(/straight away/)).not.toBeInTheDocument();
  });
});

describe('Announcements (admin) - publish, unpublish, delete', () => {
  const rowAction = async (rowName, buttonName) => userEvent.click(within(await screen.findByRole('row', { name: rowName })).getByRole('button', { name: buttonName }));

  it('a draft offers Publish (confirmed), a published one offers Unpublish', async () => {
    api.post.mockResolvedValue(item());
    renderPage();
    await loaded();
    expect(within(screen.getByRole('row', { name: /Mid-term exam/ })).queryByRole('button', { name: /^Publish / })).not.toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /Room change/ })).queryByRole('button', { name: /^Unpublish / })).not.toBeInTheDocument();
    await rowAction(/Room change/, 'Publish Room change for CS301');
    const dialog = await screen.findByRole('dialog', { name: 'Publish this announcement?' });
    expect(within(dialog).getByText(/visible to all faculty and students/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));
    expect(api.post).toHaveBeenCalledWith('/announcements/2/publish', {});
    expect(await screen.findByText('Announcement published')).toBeInTheDocument();
  });

  it('unpublishing is confirmed and moves it back to drafts', async () => {
    api.post.mockResolvedValue(item({ status: 'draft' }));
    renderPage();
    await rowAction(/Mid-term exam/, 'Unpublish Mid-term exam schedule');
    const dialog = await screen.findByRole('dialog', { name: 'Move this announcement back to drafts?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Unpublish' }));
    expect(api.post).toHaveBeenCalledWith('/announcements/1/unpublish', {});
    expect(await screen.findByText('Moved back to drafts')).toBeInTheDocument();
  });

  it('delete asks first, warns that readers lose a published one, and then deletes', async () => {
    api.delete.mockResolvedValue({});
    renderPage();
    await rowAction(/Mid-term exam/, 'Delete Mid-term exam schedule');
    const dialog = await screen.findByRole('dialog', { name: 'Delete this announcement?' });
    expect(within(dialog).getByText(/disappear for faculty and students/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    expect(api.delete).toHaveBeenCalledWith('/announcements/1');
    expect(await screen.findByText('Announcement deleted')).toBeInTheDocument();
  });

  it('deleting a draft does not mention readers', async () => {
    renderPage();
    await rowAction(/Room change/, 'Delete Room change for CS301');
    expect(screen.queryByText(/disappear for faculty/)).not.toBeInTheDocument();
  });

  it('cancelling does nothing', async () => {
    renderPage();
    await rowAction(/Mid-term exam/, 'Delete Mid-term exam schedule');
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('reports a server refusal as an error toast', async () => {
    api.delete.mockRejectedValue(new Error('Announcement not found.'));
    renderPage();
    await rowAction(/Mid-term exam/, 'Delete Mid-term exam schedule');
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete the announcement')).toBeInTheDocument();
    expect(screen.getByText('Announcement not found.')).toBeInTheDocument();
  });
});

describe('announcement helpers', () => {
  const form = (over = {}) => ({ title: 'Library timings', message: 'Open until 8 pm.', category: 'general', ...over });

  it('validates like the server', () => {
    expect(validateAnnouncement(form())).toEqual({});
    expect(validateAnnouncement(form({ title: '  ' })).title).toBe('Enter a title.');
    expect(validateAnnouncement(form({ title: 'ab' })).title).toMatch(/3 to 200/);
    expect(validateAnnouncement(form({ title: 'x'.repeat(201) })).title).toMatch(/3 to 200/);
    expect(validateAnnouncement(form({ message: '' })).message).toBe('Write the announcement.');
    expect(validateAnnouncement(form({ message: 'abcd' })).message).toMatch(/5 to 5000/);
    expect(validateAnnouncement(form({ message: 'x'.repeat(5001) })).message).toMatch(/5 to 5000/);
    expect(validateAnnouncement(form({ category: 'sports' })).category).toBe('Choose a category.');
    expect(validateAnnouncement(form({ title: 'abc', message: '12345' }))).toEqual({});
  });

  it('builds a trimmed payload with only the editable fields', () => {
    expect(toPayload(form({ title: '  A title ', message: ' text here ' }))).toEqual({ title: 'A title', message: 'text here', category: 'general' });
  });

  it('formats dates and excerpts', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatDate('2026-11-10T09:00:00')).toMatch(/2026/);
    expect(excerpt('short text')).toBe('short text');
    expect(excerpt('word '.repeat(100), 50).endsWith('…')).toBe(true);
    expect(excerpt('word '.repeat(100), 50).length).toBeLessThanOrEqual(51);
    expect(excerpt('line one\n\nline two')).toBe('line one line two');
  });
});
