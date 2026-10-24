import { useId, useState } from 'react';
import Icon from './Icon.jsx';

/*
 * Read-only weekly timetable. Presentation only: the caller supplies real data.
 *
 *   days:    [{ key: 0..6 (Mon=0), label: 'Mon', name: 'Monday' }]
 *   periods: [{ key, start: '09:00', end: '10:00', kind: 'class' | 'break' }]
 *   entries: [{ id, dayKey, periodKey, span?: 1, title, lines?: string[], kind?: 'theory' | 'lab' }]
 *
 * Wide screens: week grid (or day list via the toggle). Phones: always the day list.
 */
const todayKey = () => (new Date().getDay() + 6) % 7; // JS: Sun=0 -> our Mon=0

export default function WeeklyTimetable({ days, periods, entries, emptyHint = 'No classes scheduled.' }) {
  const today = todayKey();
  const [mode, setMode] = useState('week');
  const [dayKey, setDayKey] = useState(days.some((d) => d.key === today) ? today : days[0]?.key);
  const tabsId = useId();

  const cellOf = (dKey, pKey) => entries.find((e) => e.dayKey === dKey && e.periodKey === pKey);
  // Cells covered by a multi-period entry (e.g. a 2-period lab) must not render again.
  const covered = new Set();
  entries.forEach((e) => {
    const start = periods.findIndex((p) => p.key === e.periodKey);
    for (let i = 1; i < (e.span || 1); i += 1) {
      if (periods[start + i]) covered.add(`${e.dayKey}:${periods[start + i].key}`);
    }
  });

  const time = (p) => (
    <>
      {p.start}<small>{p.end}</small>
    </>
  );

  const entryCard = (e) => (
    <div className={`tt-entry${e.kind === 'lab' ? ' is-lab' : ''}`}>
      {e.kind && <span className="tt-kind">{e.kind === 'lab' ? 'Lab' : 'Theory'}</span>}
      <strong>{e.title}</strong>
      {(e.lines || []).map((line) => <span key={line}>{line}</span>)}
    </div>
  );

  const dayIndex = days.findIndex((d) => d.key === dayKey);
  const step = (delta) => setDayKey(days[(dayIndex + delta + days.length) % days.length].key);
  const dayEntries = entries.filter((e) => e.dayKey === dayKey);

  return (
    <div className={`tt mode-${mode}`}>
      <div className="tt-toolbar">
        <div className="tabs" role="tablist" aria-label="Day of week" id={tabsId}>
          {days.map((d) => (
            <button
              key={d.key}
              type="button"
              role="tab"
              aria-selected={d.key === dayKey}
              onClick={() => { setDayKey(d.key); setMode('day'); }}
            >
              {d.label}{d.key === today ? ' · Today' : ''}
            </button>
          ))}
        </div>
        <div className="tt-view-toggle segmented" role="group" aria-label="View">
          <button type="button" aria-pressed={mode === 'week'} onClick={() => setMode('week')}>Week</button>
          <button type="button" aria-pressed={mode === 'day'} onClick={() => setMode('day')}>Day</button>
        </div>
      </div>

      {entries.length === 0 && <p className="text-muted">{emptyHint}</p>}

      <div className="tt-week">
        <table className="tt-table">
          <caption className="sr-only">Weekly timetable</caption>
          <thead>
            <tr>
              <th scope="col" className="tt-time">Time</th>
              {days.map((d) => (
                <th key={d.key} scope="col" className={d.key === today ? 'is-today' : ''}>
                  {d.label}{d.key === today && <small>Today</small>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {periods.map((p) => (
              <tr key={p.key}>
                <th scope="row" className="tt-time">{time(p)}</th>
                {p.kind === 'break' ? (
                  <td className="tt-break" colSpan={days.length}>Break</td>
                ) : (
                  days.map((d) => {
                    if (covered.has(`${d.key}:${p.key}`)) return null;
                    const e = cellOf(d.key, p.key);
                    return (
                      <td key={d.key} rowSpan={e?.span || 1} className={d.key === today ? 'is-today' : ''}>
                        {e ? entryCard(e) : <div className="tt-free" aria-label="Free">–</div>}
                      </td>
                    );
                  })
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="tt-day" aria-label={`${days[dayIndex]?.name ?? ''} schedule`}>
        <div className="tt-day-nav">
          <button type="button" className="icon-btn" onClick={() => step(-1)} aria-label="Previous day"><Icon name="chevron-left" /></button>
          <h2>{days[dayIndex]?.name}</h2>
          <button type="button" className="icon-btn" onClick={() => step(1)} aria-label="Next day"><Icon name="chevron-right" /></button>
        </div>
        <ul className="tt-day-list">
          {periods.map((p) => {
            if (covered.has(`${dayKey}:${p.key}`)) return null;
            const e = dayEntries.find((x) => x.periodKey === p.key);
            return (
              <li key={p.key}>
                <div className="tt-day-time">{time(p)}</div>
                {p.kind === 'break' ? <div className="tt-day-break">Break</div> : e ? entryCard(e) : <div className="tt-day-free">Free</div>}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
