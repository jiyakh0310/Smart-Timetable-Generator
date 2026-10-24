import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { hrefFor, NAV } from '../../app/navConfig.js';
import DashboardHero from '../../components/DashboardHero.jsx';
import { Badge, Card, Notice, Skeleton, StatCard, StatusBadge, TIMETABLE_STATUS } from '../../components/ui';
import { useAuth } from '../../app/AuthContext.jsx';
import { api } from '../../services/api.js';

const STATS = [
  { key: 'faculty', label: 'Faculty', icon: 'users', nav: 'faculty' },
  { key: 'students', label: 'Students', icon: 'cap', nav: 'students' },
  { key: 'batches', label: 'Batches', icon: 'layers', nav: 'batches' },
  { key: 'subjects', label: 'Subjects', icon: 'book', nav: 'subjects' },
  { key: 'rooms', label: 'Rooms & labs', icon: 'building', nav: 'rooms' },
  { key: 'time_slots', label: 'Time slots', icon: 'clock', nav: 'time-slots' },
];

// The SRS workflow: data must exist before a timetable can be generated.
const SETUP = [
  { key: 'faculty', label: 'Faculty added', nav: 'faculty' },
  { key: 'batches', label: 'Batches created', nav: 'batches' },
  { key: 'subjects', label: 'Subjects defined', nav: 'subjects' },
  { key: 'rooms', label: 'Rooms and labs configured', nav: 'rooms' },
  { key: 'time_slots', label: 'Time slots configured', nav: 'time-slots' },
  { key: 'teaching_assignments', label: 'Teaching assignments set', nav: 'assignments' },
];

const PIPELINE = ['draft', 'validated', 'pending_approval', 'approved', 'published'];
const navItem = (path) => NAV.admin.find((i) => i.path === path);

function SetupAction({ step }) {
  const item = step.nav && navItem(step.nav);
  if (!item) return <Badge>Planned · M2</Badge>;
  return item.done
    ? <Link to={hrefFor('admin', item)}>Manage</Link>
    : <span><Link to={hrefFor('admin', item)}>Open</Link> <Badge>Planned · {item.milestone}</Badge></span>;
}

export default function AdminDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/admin/summary').then(setSummary).catch((e) => setError(e.message));
  }, []);

  const hero = <DashboardHero name={user.full_name} subtitle="Set up your academic data, then generate, review and publish timetables." chips={['Administrator']} />;
  if (error) return <>{hero}<Notice>{error}</Notice></>;
  if (!summary) {
    return (
      <>
        {hero}
        <div className="stat-grid" aria-busy="true" aria-label="Loading overview">
          {STATS.map((s) => <Skeleton key={s.key} height={104} />)}
        </div>
      </>
    );
  }

  const { counts, timetables } = summary;
  const readyCount = SETUP.filter((s) => counts[s.key] > 0).length;
  const allReady = readyCount === SETUP.length;

  return (
    <>
      {hero}

      <div className="stat-grid">
        {STATS.map((s) => {
          const item = navItem(s.nav);
          return <StatCard key={s.key} label={s.label} value={counts[s.key]} icon={s.icon} to={hrefFor('admin', item)} />;
        })}
      </div>

      <div className="grid-main-side">
        <Card
          flush
          title="Setup progress"
          description="All of this must be in place before a timetable can be generated."
          action={<Badge tone={allReady ? 'success' : 'warning'} dot>{readyCount} of {SETUP.length} ready</Badge>}
        >
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Setup steps and how many records exist</caption>
              <thead>
                <tr><th scope="col">Step</th><th scope="col" className="num">Records</th><th scope="col">Status</th><th scope="col">Action</th></tr>
              </thead>
              <tbody>
                {SETUP.map((step) => {
                  const n = counts[step.key];
                  return (
                    <tr key={step.key}>
                      <th scope="row">{step.label}</th>
                      <td className="num">{n}</td>
                      <td><Badge tone={n > 0 ? 'success' : 'neutral'} dot>{n > 0 ? 'Ready' : 'Missing'}</Badge></td>
                      <td><SetupAction step={step} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Timetable pipeline" description={timetables.total === 0 ? 'No timetable generated yet. Generation arrives in Milestone 4.' : `${timetables.total} timetable version(s)`}>
          <ol className="pipeline">
            {PIPELINE.map((status, i) => {
              const n = timetables.by_status[status];
              return (
                <li key={status} className={n > 0 ? 'has-items' : ''}>
                  <span className="pipeline-step">{i + 1}</span>
                  <div>
                    <strong>{TIMETABLE_STATUS[status].label}</strong>
                    <small>{TIMETABLE_STATUS[status].help}</small>
                  </div>
                  <span className="pipeline-count">{n}</span>
                </li>
              );
            })}
          </ol>
          <div className="pipeline-side">
            <span>Also:</span>
            <StatusBadge status="rejected" /> {timetables.by_status.rejected}
            <StatusBadge status="archived" /> {timetables.by_status.archived}
          </div>
        </Card>
      </div>
    </>
  );
}
