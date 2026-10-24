import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../components/ui';
import SubjectsPage from './SubjectsPage.jsx';
import { sessionsText, validateSubject } from './subjects.js';

const api = { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() };
vi.mock('../../services/api.js', () => ({ api: { get: (...a) => api.get(...a), post: (...a) => api.post(...a), patch: (...a) => api.patch(...a), delete: (...a) => api.delete(...a) } }));

const DEPARTMENTS = { items: [{ id: 1, code: 'CSE', name: 'Computer Science' }, { id: 2, code: 'ECE', name: 'Electronics' }] };
const subject = (over = {}) => ({
  id: 1, code: 'CS301', name: 'Data Structures', department: { id: 1, code: 'CSE', name: 'Computer Science' }, semester_no: 3, credits: 4,
  weekly_hours: 4, class_type: 'theory', lab_block_periods: 2, required_room_type: 'classroom', sessions_per_week: 4,
  usage: { teaching_assignments: 2, timetable_entries: 0 }, in_use: true, ...over,
});
const FREE = subject({ id: 3, code: 'CS401', name: 'Computer Networks', semester_no: 4, in_use: false, usage: { teaching_assignments: 0, timetable_entries: 0 } });
const LAB = subject({ id: 2, code: 'CS351', name: 'Data Structures Lab', class_type: 'lab', weekly_hours: 2, credits: 2, required_room_type: 'lab', sessions_per_week: 1 });
const SUBJECTS = [subject(), LAB, FREE];
const listOf = (items) => ({ items, page: 1, per_page: 10, total: items.length, pages: 1 });

const renderPage = () => render(<MemoryRouter><ToastProvider><SubjectsPage /></ToastProvider></MemoryRouter>);
const gets = () => api.get.mock.calls.map((c) => c[0]);
const lastList = () => gets().filter((u) => u.startsWith('/subjects')).at(-1);
const loaded = () => screen.findByRole('row', { name: /CS401/ });

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : listOf(SUBJECTS)));
});

async function openCreate() {
  await loaded();
  await userEvent.click(screen.getByRole('button', { name: /Add subject/ }));
  return screen.getByRole('dialog', { name: 'Add subject' });
}
async function fillTheory(dialog, over = {}) {
  const v = { code: 'cs402', name: 'Compiler Design', semester: '4', credits: '3', hours: '3', ...over };
  await userEvent.type(within(dialog).getByLabelText('Subject code'), v.code);
  await userEvent.type(within(dialog).getByLabelText('Subject name'), v.name);
  await userEvent.selectOptions(within(dialog).getByLabelText('Department'), '1');
  await userEvent.type(within(dialog).getByLabelText('Semester'), v.semester);
  await userEvent.type(within(dialog).getByLabelText('Credits'), v.credits);
  await userEvent.type(within(dialog).getByLabelText('Weekly hours'), v.hours);
}

describe('Subjects screen - listing', () => {
  it('shows real rows with type, room and assignment status', async () => {
    renderPage();
    const row = await screen.findByRole('row', { name: /CS301/ });
    expect(within(row).getByText('Data Structures')).toBeInTheDocument();
    expect(within(row).getByText('Theory')).toBeInTheDocument();
    expect(within(row).getByText('Classroom')).toBeInTheDocument();
    expect(within(row).getByText('2 batches')).toBeInTheDocument();
    expect(within(row).getByText('4 periods')).toBeInTheDocument();
    const labRow = screen.getByRole('row', { name: /CS351/ });
    expect(within(labRow).getByText('Laboratory')).toBeInTheDocument();
    expect(within(labRow).getByText('1 session × 2 periods')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /CS401/ })).getByText('Not assigned')).toBeInTheDocument();
    expect(screen.getByText(/Showing/)).toHaveTextContent('1-3 of 3 subjects');
    expect(lastList()).toBe('/subjects?page=1&per_page=10');
    expect(screen.getByRole('heading', { level: 1, name: 'Subjects' })).toBeInTheDocument();
  });

  it('sends department, semester and type filters and the search text', async () => {
    renderPage();
    await loaded();
    await screen.findByRole('option', { name: 'CSE' }); // departments loaded into the filter
    await userEvent.selectOptions(screen.getByLabelText('Department'), 'CSE');
    await waitFor(() => expect(lastList()).toContain('department_id=1'));
    await userEvent.selectOptions(screen.getByLabelText('Semester'), 'Semester 3');
    await waitFor(() => expect(lastList()).toContain('semester_no=3'));
    await userEvent.selectOptions(screen.getByLabelText('Type'), 'Lab');
    await waitFor(() => expect(lastList()).toContain('class_type=lab'));
    await userEvent.type(screen.getByRole('searchbox', { name: /Search subjects/ }), 'data');
    await waitFor(() => expect(lastList()).toContain('q=data'));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(lastList()).toBe('/subjects?page=1&per_page=10'));
  });

  it('shows an empty state with an Add button, and an error state with retry', async () => {
    api.get.mockImplementation((path) => (path === '/departments' ? Promise.resolve(DEPARTMENTS) : Promise.resolve(listOf([]))));
    const { unmount } = renderPage();
    expect(await screen.findByRole('heading', { name: 'No subjects yet' })).toBeInTheDocument();
    unmount();

    api.get.mockImplementation((path) => (path === '/departments' ? Promise.resolve(DEPARTMENTS) : Promise.reject(new Error('Cannot reach the server.'))));
    renderPage();
    expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    api.get.mockImplementation((path) => Promise.resolve(path === '/departments' ? DEPARTMENTS : listOf(SUBJECTS)));
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await loaded()).toBeInTheDocument();
  });
});

describe('Subjects screen - create form (DIY-TC05, TC07, TC08)', () => {
  it('opens with focus on the first field and offers the departments from the API', async () => {
    renderPage();
    const dialog = await openCreate();
    expect(within(dialog).getByLabelText('Subject code')).toHaveFocus();
    expect(within(dialog).getByRole('option', { name: 'CSE · Computer Science' })).toBeInTheDocument();
    expect(within(dialog).queryByLabelText(/Lab session length/)).not.toBeInTheDocument();
  });

  it('DIY-TC07: an empty form reports every required field and sends nothing', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    expect(await within(dialog).findByText('Enter the subject code, e.g. CS301.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter the subject name.')).toBeInTheDocument();
    expect(within(dialog).getByText('Choose a department.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 1 to 12.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 0 to 20.')).toBeInTheDocument();
    expect(within(dialog).getByText('Enter a whole number from 1 to 40.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects a code with illegal characters', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.type(within(dialog).getByLabelText('Subject code'), 'cs 3!');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    expect(await within(dialog).findByText(/Use up to 20 letters, digits/)).toBeInTheDocument();
  });

  it('DIY-TC05: sends a valid theory subject, then toasts, closes and reloads the list', async () => {
    api.post.mockResolvedValue(subject({ id: 9, code: 'CS402' }));
    renderPage();
    const dialog = await openCreate();
    await fillTheory(dialog);
    const before = gets().length;
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/subjects', {
      code: 'cs402', name: 'Compiler Design', department_id: 1, semester_no: 4, credits: 3, weekly_hours: 3, class_type: 'theory', required_room_type: 'classroom',
    }));
    expect(await screen.findByText('Subject created')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(gets().length).toBeGreaterThan(before);
  });

  it('DIY-TC08: choosing Lab shows the session length, limits the room to Laboratory and sends both', async () => {
    api.post.mockResolvedValue(LAB);
    renderPage();
    const dialog = await openCreate();
    await fillTheory(dialog, { code: 'cs452', name: 'Networks Lab', hours: '4' });
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Lab');
    expect(within(dialog).getByLabelText(/Lab session length/)).toHaveValue(2);
    const room = within(dialog).getByLabelText('Room requirement');
    expect(within(room).getAllByRole('option').map((o) => o.textContent)).toEqual(['Laboratory']);
    expect(room).toHaveValue('lab');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/subjects', expect.objectContaining({ class_type: 'lab', lab_block_periods: 2, required_room_type: 'lab', weekly_hours: 4 })));
  });

  it('rejects lab hours that do not fit whole sessions', async () => {
    renderPage();
    const dialog = await openCreate();
    await fillTheory(dialog, { hours: '3' });
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Lab'); // session length 2, hours 3
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    expect(await within(dialog).findByText('Lab hours must be a multiple of the session length (2).')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('switching Lab back to Theory restores the classroom options', async () => {
    renderPage();
    const dialog = await openCreate();
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Lab');
    await userEvent.selectOptions(within(dialog).getByLabelText('Type'), 'Theory');
    const room = within(dialog).getByLabelText('Room requirement');
    expect(room).toHaveValue('classroom');
    expect(within(room).getAllByRole('option')).toHaveLength(3);
    expect(within(dialog).queryByLabelText(/Lab session length/)).not.toBeInTheDocument();
  });

  it('shows a duplicate-code error from the server on the field and keeps what was typed', async () => {
    api.post.mockRejectedValue(Object.assign(new Error('A subject with code CS402 already exists.'), { details: { code: 'This code is already used.' } }));
    renderPage();
    const dialog = await openCreate();
    await fillTheory(dialog);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create subject' }));
    expect(await within(dialog).findByText('This code is already used.')).toBeInTheDocument();
    expect(within(dialog).getByText('A subject with code CS402 already exists.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Subject name')).toHaveValue('Compiler Design');
    expect(within(dialog).getByRole('button', { name: 'Create subject' })).toBeEnabled();
  });
});

describe('Subjects screen - edit (DIY-TC06)', () => {
  it('prefills an unused subject and lets every field be changed', async () => {
    api.patch.mockResolvedValue(FREE);
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CS401 Computer Networks' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit CS401' });
    expect(within(dialog).getByLabelText('Subject name')).toHaveValue('Computer Networks');
    expect(within(dialog).getByLabelText('Weekly hours')).toBeEnabled();
    const hours = within(dialog).getByLabelText('Weekly hours');
    await userEvent.clear(hours);
    await userEvent.type(hours, '5');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/subjects/3', expect.objectContaining({ code: 'CS401', weekly_hours: 5, class_type: 'theory' })));
    expect(await screen.findByText('Subject updated')).toBeInTheDocument();
  });

  it('locks scheduling fields for a subject with teaching assignments but leaves name, credits and room editable', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CS301 Data Structures' }));
    const dialog = screen.getByRole('dialog', { name: 'Edit CS301' });
    expect(within(dialog).getByText(/assigned to 2 batch\(es\)/)).toBeInTheDocument();
    ['Department', 'Semester', 'Weekly hours', 'Type'].forEach((l) => expect(within(dialog).getByLabelText(l)).toBeDisabled());
    ['Subject code', 'Subject name', 'Credits', 'Room requirement'].forEach((l) => expect(within(dialog).getByLabelText(l)).toBeEnabled());
  });

  it('shows the server lock message when the server refuses a change', async () => {
    api.patch.mockRejectedValue(Object.assign(new Error('This subject is assigned to 2 batch(es), so its weekly hours cannot be changed.'), { details: { weekly_hours: 'Locked while the subject has teaching assignments.' } }));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Edit CS351 Data Structures Lab' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByLabelText(/Lab session length/)).toBeDisabled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    expect(await within(dialog).findByText(/cannot be changed/)).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Subjects screen - delete', () => {
  it('asks first; Cancel changes nothing', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS401 Computer Networks' }));
    const dialog = screen.getByRole('dialog', { name: 'Delete this subject?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('deletes an unassigned subject after confirmation, then toasts and reloads', async () => {
    api.delete.mockResolvedValue(null);
    renderPage();
    await loaded();
    const before = gets().length;
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS401 Computer Networks' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/subjects/3'));
    expect(await screen.findByText('Subject deleted')).toBeInTheDocument();
    expect(gets().length).toBeGreaterThan(before);
  });

  it('explains why an assigned subject cannot be deleted and never calls the API', async () => {
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS301 Data Structures' }));
    const dialog = screen.getByRole('dialog', { name: 'This subject is in use' });
    expect(dialog).toHaveTextContent('2 teaching assignments');
    expect(dialog).toHaveTextContent('Remove those assignments first');
    expect(within(dialog).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'OK' }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows the server message in an error toast if a delete is refused', async () => {
    api.delete.mockRejectedValue(new Error('This subject is used by 1 teaching assignment and cannot be deleted.'));
    renderPage();
    await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Delete CS401 Computer Networks' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete the subject')).toBeInTheDocument();
    expect(screen.getByText(/cannot be deleted/)).toBeInTheDocument();
  });
});

describe('subject form rules (unit)', () => {
  const ok = { code: 'CS301', name: 'Data Structures', department_id: '1', semester_no: '3', credits: '4', weekly_hours: '4', class_type: 'theory', lab_block_periods: '2' };

  it('accepts a valid subject and normalises spacing/case for the code check', () => {
    expect(validateSubject(ok)).toEqual({});
    expect(validateSubject({ ...ok, code: ' cs-301 ' })).toEqual({});
  });

  it.each([
    [{ semester_no: '0' }, 'semester_no'], [{ semester_no: '13' }, 'semester_no'], [{ credits: '-1' }, 'credits'], [{ credits: '2.5' }, 'credits'],
    [{ weekly_hours: '0' }, 'weekly_hours'], [{ weekly_hours: '41' }, 'weekly_hours'], [{ name: 'x' }, 'name'], [{ department_id: '' }, 'department_id'],
    [{ class_type: 'lab', weekly_hours: '3', lab_block_periods: '2' }, 'weekly_hours'], [{ class_type: 'lab', lab_block_periods: '9' }, 'lab_block_periods'],
  ])('flags %j', (over, field) => {
    expect(validateSubject({ ...ok, ...over })).toHaveProperty(field);
  });

  it('describes weekly sessions for theory and lab', () => {
    expect(sessionsText({ class_type: 'theory', sessions_per_week: 1 })).toBe('1 period');
    expect(sessionsText({ class_type: 'lab', sessions_per_week: 2, lab_block_periods: 2 })).toBe('2 sessions × 2 periods');
  });
});
