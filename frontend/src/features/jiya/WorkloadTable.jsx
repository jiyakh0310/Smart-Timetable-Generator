// Jiya/Isha - R14: weekly teaching hours per faculty member against their maximum.
import { DataTable } from '../../components/data';
import { Badge } from '../../components/ui';

export const WORKLOAD_STATUS = {
  ok: { tone: 'success', label: 'Within limit' },
  at_limit: { tone: 'info', label: 'At the limit' },
  over_assigned: { tone: 'warning', label: 'Assigned over limit' },
  over_limit: { tone: 'danger', label: 'Over limit' },
  no_limit: { tone: 'neutral', label: 'No limit set' },
};

const h = (n) => `${n} h`;

export default function WorkloadTable({ rows, caption = 'Faculty weekly teaching hours' }) {
  const columns = [
    { key: 'name', header: 'Faculty', cell: (r) => (<span className="cell-stack"><strong>{r.name}</strong><small className="text-muted mono">{r.employee_code}</small></span>) },
    { key: 'scheduled', header: 'Scheduled', cell: (r) => h(r.scheduled_hours) },
    { key: 'assigned', header: 'Assigned (at least)', cell: (r) => h(r.assigned_hours) },
    { key: 'max', header: 'Maximum', cell: (r) => (r.max_hours === null ? 'Not set' : h(r.max_hours)) },
    {
      key: 'status',
      header: 'Status',
      cell: (r) => {
        const meta = WORKLOAD_STATUS[r.status] || { tone: 'neutral', label: r.status };
        const extra = r.status === 'over_limit' ? ` · ${h(r.overload_hours)} over` : r.status === 'over_assigned' || (r.status === 'at_limit' && r.over_assigned_hours > 0) ? ` · ${h(r.over_assigned_hours)} unplaceable` : '';
        return <Badge tone={r.status === 'at_limit' && r.over_assigned_hours > 0 ? 'warning' : meta.tone}>{meta.label}{extra}</Badge>;
      },
    },
  ];
  return <DataTable caption={caption} columns={columns} rows={rows} rowKey={(r) => r.faculty_id} emptyTitle="No faculty workload" emptyText="No teaching assignments exist for this term." />;
}
