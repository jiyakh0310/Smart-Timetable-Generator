import { useAuth } from '../../app/AuthContext.jsx';
import DashboardHero from '../../components/DashboardHero.jsx';
import FeaturePending from '../../components/FeaturePending.jsx';
import { Notice, StatCard } from '../../components/ui';

export default function FacultyDashboard() {
  const { user } = useAuth();
  const f = user.faculty;

  return (
    <>
      <DashboardHero
        name={user.full_name}
        subtitle="Your published teaching schedule, classrooms and weekly workload will appear here."
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
        <FeaturePending title="Today's classes" icon="calendar" req="R11" milestone="M6">
          Once the administrator publishes a timetable, your classes for today and the week appear here.
        </FeaturePending>
        <FeaturePending title="Availability & preferences" icon="clock" req="R13" milestone="M8">
          You will be able to mark the time slots you can teach and prefer.
        </FeaturePending>
      </div>
    </>
  );
}
