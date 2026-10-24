# UI Design System (Milestone 2A)

Direction: clean academic SaaS - white surfaces on a neutral background, one indigo accent, restrained radii and shadows. System font stack (no web-font download). Depth is limited to layered cards, hover lift and one CSS-only 3D accent on the dashboard hero and login panel (no 3D library).

## Where things live
| What | Location |
|---|---|
| Design tokens (colour, type, spacing, radii, shadows, motion) | `frontend/src/styles/tokens.css` |
| Reset and typography | `styles/base.css` |
| Shell, sidebar, topbar, page header, grids, breakpoints | `styles/layout.css` |
| Buttons, fields, badges, cards, tables, dialog, toast, user menu | `styles/components.css` |
| Hero, login, planned-feature page, status pipeline, weekly timetable | `styles/pages.css` |
| React components (import from `components/ui`) | `src/components/ui/` |
| Shell pieces | `components/AppShell.jsx`, `UserMenu.jsx`, `DashboardHero.jsx`, `FeaturePending.jsx` |

Rule: never write a raw colour in a component or page; use a token.

## Components (`components/ui`)
`Button`, `ButtonLink` (primary, secondary, ghost, danger; loading state) - `TextField`, `SelectField` (label, hint, error wired by id) - `Badge`, `StatusBadge` (timetable lifecycle), `PriorityBadge` - `Card`, `StatCard` - `Notice`, `EmptyState`, `Loading`, `Skeleton` - `Dialog`, `ConfirmDialog` - `ToastProvider` / `useToast` - `PageHeader`, `Breadcrumbs` - `WeeklyTimetable` - `Icon` (one 24px stroke set).

## Accessibility measures
- Visible 3px focus ring on every control; controls are 40px tall (32px for the compact size).
- One `h1` per page (via `PageHeader` / `DashboardHero`), which also sets the browser tab title.
- Skip link, landmarks (`nav`, `main`), `aria-current` on the active nav link, breadcrumb `nav`.
- Dialog: modal semantics, focus moves in, Tab is trapped, Escape closes, focus returns to the opener.
- Errors are announced (`role="alert"`) and tied to fields (`aria-describedby`, `aria-invalid`).
- Status and lab/theory are conveyed by text as well as colour.
- `prefers-reduced-motion` disables animation.
- Contrast was computed for every text/background token pair: all text pairs >= 4.5:1; form-control borders 3.7:1 (>= 3:1).

## Responsive behaviour
- Above 960px: fixed sidebar. At 960px and below: slide-in drawer (menu button, scrim, Escape to close).
- Weekly timetable: week grid on wide screens; day list with day tabs and prev/next on phones.
- Stat cards reflow to two columns at 480px; tables scroll horizontally inside their card.

## Honesty rules
No sample data ships in the UI. A screen whose backend does not exist shows "Not available yet" with its owner, requirement and milestone. `WeeklyTimetable` is tested with fixtures only and will be connected to real data when the timetable endpoints exist (M6).

## Shared list/table pattern (Milestone 2)
Every management screen is built from the same parts; `features/diya/TimeSlotsPage.jsx` is the reference.
- `hooks/useListQuery` - server-side paging, debounced search, filters, stale-response protection, step-back when a page empties, `reload()`.
- `components/data`: `DataTable` (loading skeleton, error + retry, empty vs "no results" states, dimmed refresh), `Pagination`, `TableToolbar` / `SearchBox` / `FilterSelect`.
- `components/ui`: `FormDialog` (focus starts on the first field), `CheckboxGroup`, `CheckboxField`, `ConfirmDialog`, `useToast`.
- Flow: add/edit in a dialog with client-side validation that mirrors the server; server errors map back onto the fields; delete asks for confirmation; success and failure are announced with a toast.
