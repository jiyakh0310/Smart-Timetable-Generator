import usePageTitle from '../hooks/usePageTitle.js';

// Layered, CSS-only accent: depth without a 3D library. Purely decorative (hidden from assistive tech).
export function DepthAccent() {
  return (
    <div className="depth" aria-hidden="true">
      <div className="depth-stack">
        {[0, 1, 2].map((i) => <div key={i} className="depth-layer" style={{ '--i': i }} />)}
      </div>
    </div>
  );
}

export function greeting(date = new Date()) {
  const h = date.getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

export const todayLabel = (date = new Date()) =>
  date.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

// "Dr. Rakesh Sharma" -> "Dr. Rakesh";  "Aarav Singh" -> "Aarav"
export function displayName(full) {
  const [first, second] = full.trim().split(/\s+/);
  return /^(dr|prof)\.?$/i.test(first) && second ? `${first} ${second}` : first;
}

// The dashboard's single <h1>.
export default function DashboardHero({ name, subtitle, chips = [] }) {
  const title = `${greeting()}, ${displayName(name)}`;
  usePageTitle('Dashboard');
  return (
    <section className="hero">
      <DepthAccent />
      <div className="hero-body">
        <h1>{title}</h1>
        <p>{subtitle}</p>
        <div className="hero-meta">
          <span className="hero-chip">{todayLabel()}</span>
          {chips.map((c) => <span key={c} className="hero-chip">{c}</span>)}
        </div>
      </div>
    </section>
  );
}
