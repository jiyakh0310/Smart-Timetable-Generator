import { useAuth } from '../../app/AuthContext.jsx';
import DashboardHero from '../../components/DashboardHero.jsx';
import FeaturePending from '../../components/FeaturePending.jsx';
import { ButtonLink, Card, EmptyState, Notice, StatCard } from '../../components/ui';

export default function StudentDashboard() {
  const { user } = useAuth();
  const s = user.student;

  return (
    <>
      <DashboardHero
        name={user.full_name}
        subtitle="Your batch's published timetable. You have read-only access."
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
        <Card title="My timetable">
          <EmptyState title="Your batch's published timetable" icon="calendar" action={<ButtonLink variant="primary" to="/student/timetable">Open my timetable</ButtonLink>}>
            See your classes, teachers and rooms for the week once the administrator has published the timetable.
          </EmptyState>
        </Card>
        <FeaturePending title="Announcements" icon="bell" req="R19" milestone="M9">
          Timetable and classroom changes will be posted here.
        </FeaturePending>
      </div>
    </>
  );
}
