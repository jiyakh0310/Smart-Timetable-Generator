import { describe, expect, it } from 'vitest';
import { needText, toAssignmentPayload, validateAssignment, weeklyNeed } from './assignments.js';

describe('weekly requirement wording (mirrors the server rule)', () => {
  it('theory: one class per weekly hour, one period each', () => {
    const need = weeklyNeed({ class_type: 'theory', weekly_hours: 4, lab_block_periods: 2 }); // theory ignores the stored lab length
    expect(need).toMatchObject({ sessions: 4, length: 1, periods: 4, valid: true, headline: '4 classes per week' });
    expect(need.detail).toBe('One period each (4 periods per week in total).');
  });

  it('lab: hours / session length sessions, each needing that many CONSECUTIVE periods', () => {
    const need = weeklyNeed({ class_type: 'lab', weekly_hours: 6, lab_block_periods: 3 });
    expect(need).toMatchObject({ sessions: 2, length: 3, periods: 6, valid: true, headline: '2 lab sessions per week' });
    expect(need.detail).toBe('Each session needs 3 consecutive periods (6 periods per week in total).');
  });

  it('uses singular wording and flags hours that are not a whole number of sessions', () => {
    expect(weeklyNeed({ class_type: 'lab', weekly_hours: 2, lab_block_periods: 2 }).headline).toBe('1 lab session per week');
    expect(weeklyNeed({ class_type: 'theory', weekly_hours: 1, lab_block_periods: 2 }).headline).toBe('1 class per week');
    expect(weeklyNeed({ class_type: 'lab', weekly_hours: 3, lab_block_periods: 2 }).valid).toBe(false);
    expect(weeklyNeed(null)).toBeNull();
  });

  it('describes API items compactly', () => {
    expect(needText({ sessions_per_week: 4, session_length: 1, periods_per_week: 4 })).toBe('4 periods/week');
    expect(needText({ sessions_per_week: 1, session_length: 1, periods_per_week: 1 })).toBe('1 period/week');
    expect(needText({ sessions_per_week: 2, session_length: 2, periods_per_week: 4 })).toBe('2 × 2 periods (4/week)');
  });
});

describe('assignment form rules', () => {
  const ok = { term_id: '1', batch_id: '2', subject_id: '3', faculty_id: '4' };

  it('needs all four choices', () => {
    expect(validateAssignment(ok)).toEqual({});
    expect(Object.keys(validateAssignment({ term_id: '', batch_id: '', subject_id: '', faculty_id: '' })).sort()).toEqual(['batch_id', 'faculty_id', 'subject_id', 'term_id']);
  });

  it('sends only the four ids - never a session count (the server calculates it)', () => {
    expect(toAssignmentPayload(ok)).toEqual({ term_id: 1, batch_id: 2, subject_id: 3, faculty_id: 4 });
  });
});
