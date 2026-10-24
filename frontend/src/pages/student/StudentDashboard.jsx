import { useAuth } from '../../app/AuthContext.jsx';
import DashboardHero from '../../components/DashboardHero.jsx';
import FeaturePending from '../../components/FeaturePending.jsx';
import { Notice, StatCard } from '../../components/ui';

export default function StudentDashboard() {
  const { user } = useAuth();
  const s = user.student;

  return (
    <>
      <DashboardHero
        name={user.full_name}
        subtitle="Your batch's published timetable will appear here. You have read-only access."
        chips={s ? [s.batch] : ['Student']}
      />
      {!s && <Notice tone="warning">Your account is not linked to a student record yet. Please contact the administrator.</Notice>}
      {s && (
        <div className="stat-grid">
          <StatCard label="Batch" value={s.batch} icon="layers" />
          <StatCard label="Semester" value={s.semester_no} icon="book" />
          <StatCard label="Program" value={s.program} icon="cap" />
          <StatCard label="Enrollment no." value={s.enrollment_no} icon="user" />
        </div>
      )}
      <div className="grid-main-side">
        <FeaturePending title="This week's timetable" icon="calendar" req="R12" milestone="M6">
          Your batch timetable (daily and weekly views, with print and download) appears here once the administrator publishes it.
        </FeaturePending>
        <FeaturePending title="Announcements" icon="bell" req="R19" milestone="M9">
          Timetable and classroom changes will be posted here.
        </FeaturePending>
      </div>
    </>
  );
}
