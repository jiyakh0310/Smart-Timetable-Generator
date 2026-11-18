import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AnnouncementFeed } from './AnnouncementFeedPage.jsx';
import LatestAnnouncements from './LatestAnnouncements.jsx';

const api = { get: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a) } }));

const a = (over = {}) => ({
  id: 1, title: 'Mid-term exam schedule', message: 'The mid-term exams start on Monday.\n\nPlease check the timetable and bring your ID card.', category: 'exam', category_label: 'Exam', status: 'published',
  published_at: '2026-11-10T09:00:00', created_at: '2026-11-09T09:00:00', updated_at: '2026-11-10T09:00:00', author: { name: 'Dr. Anita Verma' }, ...over,
});
const FEED = [a(), a({ id: 2, title: 'Water supply interruption', message: 'No water on Saturday.', category: 'urgent' }), a({ id: 3, title: 'Library timings', message: 'Open until 8 pm.', category: 'general' })];
const listOf = (items, over = {}) => ({ items, page: 1, per_page: 8, total: items.length, pages: 1, ...over });
const gets = () => api.get.mock.calls.map((c) => c[0]);
const renderFeed = (role = 'student') => render(<MemoryRouter><AnnouncementFeed role={role} /></MemoryRouter>);

beforeEach(() => {
  api.get.mockReset();
  api.get.mockResolvedValue(listOf(FEED));
});

describe.each(['student', 'faculty'])('Announcement feed (%s)', (role) => {
  it('lists the published announcements with category, date, author and a short excerpt', async () => {
    renderFeed(role);
    const list = await screen.findByRole('list', { name: 'Announcements' });
    const cards = within(list).getAllByRole('article');
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByRole('heading', { name: 'Mid-term exam schedule' })).toBeInTheDocument();
    expect(within(cards[0]).getByText('Exam')).toBeInTheDocument();
    expect(within(cards[0]).getByText(/Published .* · by Dr\. Anita Verma/)).toBeInTheDocument();
    expect(within(cards[1]).getByText('Urgent')).toBeInTheDocument();
  });

  it('only ever asks for the published feed and has no management controls', async () => {
    renderFeed(role);
    await screen.findByRole('list', { name: 'Announcements' });
    expect(gets().every((u) => u.startsWith('/announcements/published?'))).toBe(true);
    for (const name of [/New announcement/, /Publish/, /Unpublish/, /Delete/, /Edit/, /Save/]) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument();          // no draft / published filter for readers
    expect(screen.queryByText('Draft')).not.toBeInTheDocument();
  });

  it('opens the full announcement, keeping paragraph breaks, and closes with Escape', async () => {
    renderFeed(role);
    await userEvent.click(await screen.findByRole('button', { name: 'Read Mid-term exam schedule' }));
    const dialog = screen.getByRole('dialog', { name: 'Mid-term exam schedule' });
    const body = within(dialog).getByText(/Please check the timetable and bring your ID card/);
    expect(body.textContent).toBe('The mid-term exams start on Monday.\n\nPlease check the timetable and bring your ID card.');
    expect(within(dialog).getByText('Exam')).toBeInTheDocument();
    expect(within(dialog).queryByText('Published', { selector: '.badge' })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('filters by category on the server', async () => {
    renderFeed(role);
    await screen.findByRole('list', { name: 'Announcements' });
    api.get.mockResolvedValue(listOf([FEED[1]]));
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'urgent');
    await waitFor(() => expect(gets().at(-1)).toContain('category=urgent'));
    expect(await screen.findByRole('heading', { name: 'Water supply interruption' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Library timings' })).not.toBeInTheDocument();
  });

  it('searches on the server', async () => {
    renderFeed(role);
    await screen.findByRole('list', { name: 'Announcements' });
    await userEvent.type(screen.getByLabelText('Search announcements'), 'water');
    await waitFor(() => expect(gets().at(-1)).toContain('q=water'));
  });

  it('says plainly when nothing has been published', async () => {
    api.get.mockResolvedValue(listOf([]));
    renderFeed(role);
    expect(await screen.findByText('No announcements yet')).toBeInTheDocument();
    expect(screen.getByText(/once the administrator publishes them/)).toBeInTheDocument();
  });

  it('says so when a search matches nothing and offers to clear it', async () => {
    renderFeed(role);
    await screen.findByRole('list', { name: 'Announcements' });
    api.get.mockResolvedValue(listOf([]));
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'academic');
    expect(await screen.findByText('No announcements match your search')).toBeInTheDocument();
    api.get.mockResolvedValue(listOf(FEED));
    await userEvent.click(screen.getByRole('button', { name: 'Clear search and filters' }));
    expect(await screen.findByRole('list', { name: 'Announcements' })).toBeInTheDocument();
  });

  it('shows a loading state first', async () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    renderFeed(role);
    expect(await screen.findByRole('status', { name: 'Loading announcements' })).toBeInTheDocument();
  });

  it('shows the error with a working retry', async () => {
    api.get.mockRejectedValueOnce(new Error('Server unavailable'));
    renderFeed(role);
    expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('list', { name: 'Announcements' })).toBeInTheDocument();
  });

  it('pages through long feeds', async () => {
    api.get.mockResolvedValue(listOf(FEED, { total: 20, pages: 3 }));
    renderFeed(role);
    await screen.findByRole('list', { name: 'Announcements' });
    expect(document.body.textContent).toMatch(/of 20 announcements/);
    await userEvent.click(screen.getByRole('button', { name: /Next/ }));
    await waitFor(() => expect(gets().at(-1)).toContain('page=2'));
  });

  it('uses the role in the breadcrumb', async () => {
    renderFeed(role);
    expect(await screen.findByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent(role === 'student' ? 'Student portal' : 'Faculty portal');
  });
});

describe('Latest announcements (dashboard card)', () => {
  const renderCard = (role = 'student') => render(<MemoryRouter><LatestAnnouncements role={role} /></MemoryRouter>);

  it('shows the newest three with category and date, linking to the full page', async () => {
    renderCard();
    expect(await screen.findByRole('link', { name: 'Mid-term exam schedule' })).toHaveAttribute('href', '/student/announcements');
    expect(gets()).toEqual(['/announcements/published?per_page=3']);
    expect(screen.getByText('Urgent')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View all' })).toHaveAttribute('href', '/student/announcements');
  });

  it('links faculty to the faculty page', async () => {
    renderCard('faculty');
    expect(await screen.findByRole('link', { name: 'View all' })).toHaveAttribute('href', '/faculty/announcements');
  });

  it('shows a friendly empty state', async () => {
    api.get.mockResolvedValue(listOf([]));
    renderCard();
    expect(await screen.findByText('No announcements yet')).toBeInTheDocument();
  });

  it('shows an error without breaking the dashboard', async () => {
    api.get.mockRejectedValue(new Error('Server unavailable'));
    renderCard();
    expect(await screen.findByText('Server unavailable')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View all' })).toBeInTheDocument();
  });

  it('shows a loading state', () => {
    api.get.mockImplementation(() => new Promise(() => {}));
    renderCard();
    expect(screen.getByRole('status', { name: 'Loading announcements' })).toBeInTheDocument();
  });
});
