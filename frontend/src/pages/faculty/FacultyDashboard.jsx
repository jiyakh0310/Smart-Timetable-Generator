import { useAuth } from '../../app/AuthContext.jsx';
import DashboardHero from '../../components/DashboardHero.jsx';
import FeaturePending from '../../components/FeaturePending.jsx';
import { ButtonLink, Card, EmptyState, Notice, StatCard } from '../../components/ui';

export default function FacultyDashboard() {
  const { user } = useAuth();
  const f = user.faculty;

  return (
    <>
      <DashboardHero
        name={user.full_name}
        subtitle="Your published teaching schedule and classrooms. You have read-only access."
        chips={f ? [f.department, f.designation].filter(Boolean) : ['Faculty']}
      />
      {!f && <Notice tone="warning">Your account is not linked to a faculty record yet. Please contact the administrator.</Notice>}
      {f && (
        <div className="stat-grid">
          <StatCard label="Employee code" value={f.employee_code} icon="user" />
          <StatCard label="Department" value={f.department} icon="building" />
          <StatCard label="Weekly hour limit" value={`${f.max_weekly_hours} h`} icon="clock" />
        </div>
      )}
      <div className="grid-main-side">
        <Card title="My timetable">
          <EmptyState title="Your published teaching schedule" icon="calendar" action={<ButtonLink variant="primary" to="/faculty/timetable">Open my timetable</ButtonLink>}>
            See your classes, rooms and batches for the week once the administrator has published a timetable.
          </EmptyState>
        </Card>
        <FeaturePending title="Availability & preferences" icon="clock" req="R13" milestone="M8">
          You will be able to mark the time slots you can teach and prefer.
        </FeaturePending>
      </div>
    </>
  );
}
