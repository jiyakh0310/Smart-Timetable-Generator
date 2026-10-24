import { useAuth } from '../app/AuthContext.jsx';
import { crumbsFor, ROLE_LABEL } from '../app/navConfig.js';
import { initials } from '../components/UserMenu.jsx';
import { Badge, Card, PageHeader } from '../components/ui';
import { ChangePasswordForm } from '../features/isha/index.js';

function Row({ label, value }) {
  return <div><dt>{label}</dt><dd>{value || '—'}</dd></div>;
}

export default function ProfilePage() {
  const { user } = useAuth();
  const f = user.faculty;
  const s = user.student;
  return (
    <>
      <PageHeader title="My profile" description="Your account details and password." breadcrumbs={crumbsFor(user.role, 'My profile')} />
      <div className="grid-2">
        <Card title="Account">
          <div className="profile-head">
            <span className="avatar" aria-hidden="true">{initials(user.full_name)}</span>
            <div>
              <h2>{user.full_name}</h2>
              <p>{user.email}</p>
            </div>
            <Badge tone="primary">{ROLE_LABEL[user.role]}</Badge>
          </div>
          <dl className="meta-grid profile-meta">
            {f && (
              <>
                <Row label="Employee code" value={f.employee_code} />
                <Row label="Department" value={f.department} />
                <Row label="Designation" value={f.designation} />
                <Row label="Weekly hour limit" value={`${f.max_weekly_hours} h`} />
              </>
            )}
            {s && (
              <>
                <Row label="Enrollment no." value={s.enrollment_no} />
                <Row label="Program" value={s.program} />
                <Row label="Batch" value={s.batch} />
                <Row label="Department" value={s.department} />
              </>
            )}
          </dl>
        </Card>
        <Card title="Change password" description="Use at least 8 characters.">
          <ChangePasswordForm />
        </Card>
      </div>
    </>
  );
}
