import { describe, expect, it } from 'vitest';
import { buildGrid, countStatuses, isDirty, isEditable, nextStatus, statusMapOf, toEntries } from './availability.js';
import { generatePassword, passwordProblem, toFacultyPayload, validateFaculty } from './faculty.js';

const ok = { name: 'Dr. Priya Menon', email: 'priya@college.test', employee_code: 'F100', department_id: '1', designation: 'Professor', max_weekly_hours: '16', password: 'Secure#Pass42', is_active: true };

describe('faculty form rules', () => {
  it('accepts a valid new faculty member and a valid edit (no password needed)', () => {
    expect(validateFaculty(ok, 'create')).toEqual({});
    expect(validateFaculty({ ...ok, password: '' }, 'edit')).toEqual({});
  });

  it.each([
    [{ name: '' }, 'name'], [{ name: 'x' }, 'name'], [{ email: '' }, 'email'], [{ email: 'nope' }, 'email'], [{ employee_code: '' }, 'employee_code'],
    [{ employee_code: 'bad code!' }, 'employee_code'], [{ department_id: '' }, 'department_id'], [{ designation: 'd'.repeat(81) }, 'designation'],
    [{ max_weekly_hours: '0' }, 'max_weekly_hours'], [{ max_weekly_hours: '41' }, 'max_weekly_hours'], [{ max_weekly_hours: '2.5' }, 'max_weekly_hours'], [{ max_weekly_hours: '' }, 'max_weekly_hours'],
  ])('flags %j', (over, field) => expect(validateFaculty({ ...ok, ...over }, 'create')).toHaveProperty(field));

  it('requires a good password only when creating', () => {
    expect(validateFaculty({ ...ok, password: '' }, 'create')).toHaveProperty('password');
    expect(validateFaculty({ ...ok, password: 'short1' }, 'create')).toHaveProperty('password');
    expect(validateFaculty({ ...ok, password: 'bad' }, 'edit')).toEqual({});
  });

  it('builds payloads: create sends the password, edit sends is_active, neither can send a role', () => {
    const create = toFacultyPayload(ok, 'create');
    expect(create).toMatchObject({ name: 'Dr. Priya Menon', department_id: 1, max_weekly_hours: 16, password: 'Secure#Pass42' });
    expect(create).not.toHaveProperty('is_active');
    const edit = toFacultyPayload({ ...ok, designation: '  ', is_active: false }, 'edit');
    expect(edit).toMatchObject({ is_active: false, designation: null });
    expect(edit).not.toHaveProperty('password');
    [create, edit].forEach((p) => { expect(p).not.toHaveProperty('role'); expect(p).not.toHaveProperty('user_id'); });
  });
});

describe('password policy and generator', () => {
  it('matches the server rules', () => {
    expect(passwordProblem('')).toMatch(/Enter a password/);
    expect(passwordProblem('short1')).toMatch(/8 to 128/);
    expect(passwordProblem('onlyletters')).toMatch(/letter and one number/);
    expect(passwordProblem('12345678')).toMatch(/letter and one number/);
    expect(passwordProblem('Priya2024x', ['priya2024x'])).toMatch(/must not be the same/);
    expect(passwordProblem('Secure#Pass42', ['priya@college.test'])).toBe('');
  });

  it('generates 14-character passwords that always satisfy the policy and differ each time', () => {
    const seen = new Set();
    for (let i = 0; i < 200; i += 1) {
      const p = generatePassword();
      expect(p).toHaveLength(14);
      expect(passwordProblem(p)).toBe('');
      expect(p).not.toMatch(/[0O1lI]/); // no look-alike characters
      seen.add(p);
    }
    expect(seen.size).toBe(200);
  });

  it('uses the secure random source it is given', () => {
    let calls = 0;
    const rng = { getRandomValues: (a) => { calls += 1; a[0] = calls % 200; return a; } };
    expect(generatePassword(12, rng)).toHaveLength(12);
    expect(calls).toBeGreaterThanOrEqual(12);
  });
});

describe('availability grid logic', () => {
  const slot = (id, day, period, over = {}) => ({
    time_slot_id: id, day_of_week: day, day_name: ['Monday', 'Tuesday'][day], period_no: period, start_time: `0${8 + period}:00`, end_time: `0${9 + period}:00`,
    slot_type: 'class', is_active: true, status: 'available', ...over,
  });
  const slots = [slot(1, 0, 1), slot(2, 0, 2, { status: 'unavailable' }), slot(3, 1, 1), slot(4, 0, 3, { slot_type: 'break' }), slot(5, 1, 2, { is_active: false, status: 'preferred' })];

  it('cycles available -> unavailable -> preferred -> available', () => {
    expect(['available', 'unavailable', 'preferred'].map(nextStatus)).toEqual(['unavailable', 'preferred', 'available']);
  });

  it('only active class slots are editable', () => {
    expect(slots.filter(isEditable).map((s) => s.time_slot_id)).toEqual([1, 2, 3]);
  });

  it('builds rows x columns', () => {
    const g = buildGrid(slots);
    expect(g.days.map((d) => d.day_name)).toEqual(['Monday', 'Tuesday']);
    expect(g.periods.map((p) => p.period_no)).toEqual([1, 2, 3]);
    expect(g.cell(0, 2).time_slot_id).toBe(2);
    expect(g.cell(1, 3)).toBeUndefined();
  });

  it('only sends non-default settings for editable slots (never the disabled slot or breaks)', () => {
    const local = { ...statusMapOf(slots), 1: 'preferred', 3: 'unavailable' };
    expect(toEntries(slots, local)).toEqual([{ time_slot_id: 1, status: 'preferred' }, { time_slot_id: 2, status: 'unavailable' }, { time_slot_id: 3, status: 'unavailable' }]);
  });

  it('detects unsaved changes only on editable slots and counts statuses', () => {
    const saved = statusMapOf(slots);
    expect(isDirty(slots, saved, saved)).toBe(false);
    expect(isDirty(slots, saved, { ...saved, 5: 'available' })).toBe(false); // disabled slot is locked
    expect(isDirty(slots, saved, { ...saved, 1: 'preferred' })).toBe(true);
    expect(countStatuses(slots, saved)).toEqual({ unavailable: 1, preferred: 0 }); // the disabled slot's saved preference is not counted
  });
});
