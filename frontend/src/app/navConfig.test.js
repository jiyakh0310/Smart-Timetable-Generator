import { describe, expect, it } from 'vitest';
import { crumbsFor, groupNav, hrefFor, NAV, ROLES, ROLE_HOME } from './navConfig.js';

describe('navigation config', () => {
  it('has exactly the three approved roles (no Department Head / Coordinator)', () => {
    expect(ROLES).toEqual(['admin', 'faculty', 'student']);
    expect(Object.keys(NAV).sort()).toEqual(['admin', 'faculty', 'student']);
    expect(JSON.stringify(NAV).toLowerCase()).not.toMatch(/department head|coordinator/);
  });

  it('every role has a dashboard and a profile page that are marked as built', () => {
    ROLES.forEach((role) => {
      expect(NAV[role].find((i) => i.path === '')?.done).toBe(true);
      expect(NAV[role].find((i) => i.path === 'profile')?.done).toBe(true);
    });
  });

  it('every unbuilt item names its owner, requirement, priority, milestone and description', () => {
    ROLES.flatMap((r) => NAV[r]).filter((i) => !i.done).forEach((i) => {
      expect(i.owner && i.req && i.priority && i.milestone && i.blurb, i.label).toBeTruthy();
    });
  });

  it('students get no management screens', () => {
    expect(NAV.student.map((i) => i.label)).toEqual(['Dashboard', 'My Timetable', 'Announcements', 'My Profile']);
  });

  it('groups keep order and nothing is lost', () => {
    const groups = groupNav(NAV.admin);
    expect(groups.map((g) => g.group)).toEqual(['Overview', 'Academics', 'Infrastructure', 'Scheduling', 'Communication', 'Account']);
    expect(groups.flatMap((g) => g.items)).toHaveLength(NAV.admin.length);
  });

  it('builds hrefs and breadcrumbs under the role home', () => {
    expect(hrefFor('admin', { path: '' })).toBe('/admin');
    expect(hrefFor('faculty', { path: 'workload' })).toBe('/faculty/workload');
    expect(crumbsFor('student', 'My Timetable')).toEqual([{ label: 'Student portal', to: ROLE_HOME.student }, { label: 'My Timetable' }]);
  });
});
