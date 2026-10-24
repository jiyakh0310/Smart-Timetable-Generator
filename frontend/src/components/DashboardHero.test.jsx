import { describe, expect, it } from 'vitest';
import { displayName, greeting } from './DashboardHero.jsx';

describe('DashboardHero helpers', () => {
  it('keeps an academic title with the first name', () => {
    expect(displayName('Dr. Rakesh Sharma')).toBe('Dr. Rakesh');
    expect(displayName('Prof. Arjun Mehta')).toBe('Prof. Arjun');
    expect(displayName('Aarav Singh')).toBe('Aarav');
    expect(displayName('Madonna')).toBe('Madonna');
  });

  it('greets by time of day', () => {
    expect(greeting(new Date(2026, 0, 1, 8))).toBe('Good morning');
    expect(greeting(new Date(2026, 0, 1, 14))).toBe('Good afternoon');
    expect(greeting(new Date(2026, 0, 1, 20))).toBe('Good evening');
  });
});
