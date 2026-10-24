// tone: neutral | primary | success | warning | danger | info
export function Badge({ tone = 'neutral', dot = false, children }) {
  return <span className={`badge${tone !== 'neutral' ? ` badge-${tone}` : ''}${dot ? ' badge-dot' : ''}`}>{children}</span>;
}

// Timetable lifecycle: draft -> validated -> pending approval -> approved -> published (or rejected / archived).
export const TIMETABLE_STATUS = {
  draft: { label: 'Draft', tone: 'neutral', help: 'Generated, not yet checked. Only admins can see it.' },
  validated: { label: 'Validated', tone: 'info', help: 'Passed validation with no clashes.' },
  pending_approval: { label: 'Pending approval', tone: 'warning', help: 'Submitted for review.' },
  approved: { label: 'Approved', tone: 'primary', help: 'Approved, ready to publish.' },
  published: { label: 'Published', tone: 'success', help: 'Visible to faculty and students.' },
  rejected: { label: 'Rejected', tone: 'danger', help: 'Sent back with a reason.' },
  archived: { label: 'Archived', tone: 'neutral', help: 'Replaced by a newer version.' },
};

export function StatusBadge({ status }) {
  const meta = TIMETABLE_STATUS[status] || { label: status, tone: 'neutral' };
  return <Badge tone={meta.tone} dot>{meta.label}</Badge>;
}

const PRIORITY_TONE = { Must: 'danger', Should: 'warning', Could: 'info' };
export function PriorityBadge({ priority }) {
  return <Badge tone={PRIORITY_TONE[priority] || 'neutral'}>{priority}</Badge>;
}
