// Navigation for each of the three roles, grouped by function. Items without `done: true` open a clearly
// labelled "not available yet" page naming the owner, requirement and milestone - nothing pretends to work.
//
// owner: team member building it   req: MoSCoW requirement ID   priority: Must/Should/Could

export const ROLES = ['admin', 'faculty', 'student'];
export const ROLE_HOME = { admin: '/admin', faculty: '/faculty', student: '/student' };
export const ROLE_LABEL = { admin: 'Administrator', faculty: 'Faculty', student: 'Student' };
const PORTAL_LABEL = { admin: 'Admin portal', faculty: 'Faculty portal', student: 'Student portal' };

export const NAV = {
  admin: [
    { path: '', label: 'Dashboard', icon: 'grid', group: 'Overview', done: true },
    { path: 'faculty', label: 'Faculty', icon: 'users', group: 'Academics', owner: 'Isha', req: 'R2', priority: 'Must', milestone: 'M3', done: true,
      blurb: 'Add, edit and deactivate faculty members and manage their login accounts.' },
    { path: 'availability', label: 'Faculty Availability', icon: 'clock', group: 'Academics', owner: 'Isha', req: 'R13', priority: 'Should', milestone: 'M3', done: true,
      blurb: 'Mark the time slots each faculty member cannot teach (hard) or prefers (soft).' },
    { path: 'batches', label: 'Batches', icon: 'layers', group: 'Academics', owner: 'Diya', req: 'R3', priority: 'Must', milestone: 'M2', done: true,
      blurb: 'Manage batches: program, semester, section and batch strength.' },
    { path: 'students', label: 'Students', icon: 'cap', group: 'Academics', owner: 'Diya', req: 'R3', priority: 'Must', milestone: 'M2', done: true,
      blurb: 'Manage student records and assign each student to a batch.' },
    { path: 'subjects', label: 'Subjects', icon: 'book', group: 'Academics', owner: 'Diya', req: 'R4', priority: 'Must', milestone: 'M2', done: true,
      blurb: 'Manage subjects, credits, weekly hours and theory/lab classification.' },
    { path: 'assignments', label: 'Teaching Assignments', icon: 'link', group: 'Academics', owner: 'Diya', req: 'R2 / R4', priority: 'Must', milestone: 'M3', done: true,
      blurb: 'Decide which faculty member teaches which subject to which batch, and how many sessions it needs each week.' },
    { path: 'time-slots', label: 'Time Slots', icon: 'clock', group: 'Academics', owner: 'Diya', req: 'R6', priority: 'Must', milestone: 'M2', done: true,
      blurb: 'Define working days, periods and breaks.' },
    { path: 'rooms', label: 'Rooms & Labs', icon: 'building', group: 'Infrastructure', owner: 'Pragya', req: 'R5', priority: 'Must', milestone: 'M4A', done: true,
      blurb: 'Manage classrooms and laboratories: capacity, type, location and availability.' },
    { path: 'timetables', label: 'Timetables', icon: 'calendar', group: 'Scheduling', owner: 'Jiya', req: 'R7 / R10 / R11', priority: 'Must', milestone: 'M4-M5', done: true,
      blurb: 'Generate, validate, review and publish timetables; resolve clashes.' },
    { path: 'announcements', label: 'Announcements', icon: 'bell', group: 'Communication', owner: 'Isha', req: 'R19', priority: 'Could', milestone: 'M9',
      blurb: 'Publish timetable changes and academic announcements.' },
    { path: 'profile', label: 'My Profile', icon: 'user', group: 'Account', done: true },
  ],
  faculty: [
    { path: '', label: 'Dashboard', icon: 'grid', group: 'Overview', done: true },
    { path: 'timetable', label: 'My Timetable', icon: 'calendar', group: 'Teaching', owner: 'Jiya', req: 'R11', priority: 'Must', milestone: 'M6', done: true,
      blurb: 'Your published teaching schedule: subjects, batches and classrooms.' },
    { path: 'availability', label: 'Availability', icon: 'clock', group: 'Teaching', owner: 'Isha', req: 'R13', priority: 'Should', milestone: 'M8',
      blurb: 'Set your own available and preferred time slots (for now the administrator manages this).' },
    { path: 'workload', label: 'Workload', icon: 'chart', group: 'Teaching', owner: 'Isha', req: 'R14', priority: 'Should', milestone: 'M8',
      blurb: 'Your weekly teaching hours.' },
    { path: 'announcements', label: 'Announcements', icon: 'bell', group: 'Communication', owner: 'Isha', req: 'R19', priority: 'Could', milestone: 'M9',
      blurb: 'Timetable changes and academic announcements.' },
    { path: 'profile', label: 'My Profile', icon: 'user', group: 'Account', done: true },
  ],
  student: [
    { path: '', label: 'Dashboard', icon: 'grid', group: 'Overview', done: true },
    { path: 'timetable', label: 'My Timetable', icon: 'calendar', group: 'Timetable', owner: 'Diya', req: 'R12', priority: 'Must', milestone: 'M6', done: true,
      blurb: 'The published timetable for your batch (read-only).' },
    { path: 'announcements', label: 'Announcements', icon: 'bell', group: 'Communication', owner: 'Isha', req: 'R19', priority: 'Could', milestone: 'M9',
      blurb: 'Timetable changes and academic announcements.' },
    { path: 'profile', label: 'My Profile', icon: 'user', group: 'Account', done: true },
  ],
};

export const hrefFor = (role, item) => `${ROLE_HOME[role]}${item.path ? `/${item.path}` : ''}`;

// [{ group, items }] in the order groups first appear.
export function groupNav(items) {
  const groups = [];
  items.forEach((item) => {
    let g = groups.find((x) => x.group === item.group);
    if (!g) { g = { group: item.group, items: [] }; groups.push(g); }
    g.items.push(item);
  });
  return groups;
}

export const crumbsFor = (role, label) => [{ label: PORTAL_LABEL[role], to: ROLE_HOME[role] }, { label }];
