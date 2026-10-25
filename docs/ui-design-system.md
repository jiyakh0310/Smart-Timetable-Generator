# UI Design System (Milestone 2A, redesigned)

Direction: a calm, premium university product. A warm-white / light-lavender canvas with a very quiet abstract wash, deep indigo for action, dark readable text, and soft indigo-tinted depth: layered surfaces, a thin top highlight on cards and controls, small hover lifts, and one CSS-only 3D accent (stacked planes) on the dashboard hero and login hero. System font stack (no web-font download). No glassmorphism beyond the translucent top bar, no neon, no 3D library.

## Where things live
| What | Location |
|---|---|
| Design tokens (colour, type, spacing, radii, shadows, motion, layout sizes) | `frontend/src/styles/tokens.css` |
| Reset, typography, background wash, reduced motion | `styles/base.css` |
| Top navigation, page container, page header, grids, breakpoints | `styles/layout.css` |
| Buttons, fields, badges, cards, tables (grid and stacked cards), dialog, toast, account menu, timetable/review panels | `styles/components.css` |
| Hero, login, planned-feature page, status pipeline, weekly timetable | `styles/pages.css` |
| React components (import from `components/ui`) | `src/components/ui/` |
| Shell pieces | `components/AppShell.jsx`, `UserMenu.jsx`, `DashboardHero.jsx`, `FeaturePending.jsx` |
| Responsive hooks | `hooks/useMediaQuery.js`, `hooks/useStackedLayout.js` |

Rule: never write a raw colour in a component or page; use a token.

## Navigation (no sidebar)
- **Desktop (>= 1000px):** a sticky top bar: brand on the left, role-specific links across the middle, account menu on the right. Roles with many pages (Admin) group the academic pages in an **Academics** dropdown; single pages stay direct links. A small bar under the label marks the active page (and the group that contains it). Between 1000px and 1360px the bar compacts (no brand subtitle, role chip or name; below 1100px the link icons are dropped) so it always stays on one row.
- **Phones and small tablets (< 1000px):** a 60-64px header with the brand, the account avatar and a menu button. The same `<nav>` becomes a right-hand drawer with group headings and 48px tap targets. It closes on navigation, on Escape (focus returns to the menu button), on the close button and on a tap outside; Tab stays inside while it is open; background scrolling is locked. A closed drawer is `display: none`, so it is out of the tab order and cannot widen the mobile viewport.
- The profile page lives in the account menu. Admin, Faculty and Student each get only their own links (`app/navConfig.js`); no role was added.

## Components (`components/ui`)
`Button`, `ButtonLink` (**primary** main action, **secondary** supporting, **ghost** low emphasis, **danger** destructive only, **success** publishing; loading state) - `TextField`, `TextAreaField`, `PasswordField` (Show / Hide), `SelectField` (label, hint, error wired by id) - `Badge`, `StatusBadge` (Draft, Validated, Pending approval, Approved, Published, Rejected, Archived; always a text label) - `Card`, `StatCard` - `Notice`, `EmptyState`, `Loading`, `Skeleton` - `Dialog`, `ConfirmDialog` (tones: primary, danger, success) - `ToastProvider` / `useToast` - `PageHeader`, `Breadcrumbs` - `WeeklyTimetable` - `Icon` (one 24px stroke set).
Controls are 42px tall (34px for the compact size); every button has the same radius, weight and icon placement and a visible hover, focus, disabled and loading state.

## Tables: no horizontal scrolling
`components/data/DataTable` (used by every list screen, the dashboard, workload and validation tables) renders a compact, wrapping grid on wide screens and switches to **labelled stacked cards** when the columns do not fit (`hooks/useStackedLayout`): when the container is narrower than about 112px per column, and also whenever the real table turns out to overflow. Each cell carries its column header as a label, the first cell becomes the card title, and the actions stay at the bottom of the card. On tablets the cards flow into a two-column grid. ARIA table roles are kept while stacked. The availability picker shows one day at a time on phones (day tabs), and the weekly timetable shows a day view (tabs, previous / next) below 900px. Lab blocks, break rows and the move-class interaction are preserved in both.

## Timetable screens
A summary card shows name, status, "Current published version", validation state, version, term and counts, then Export PDF / Excel. **Validate** is offered only while a timetable is still editable; **Discard** only where the server allows it; the review panel (workflow steps, Submit, Approve, Reject / Withdraw, **Publish** in green) only offers the actions the server lists in `allowed_actions`. Hard validation errors (red) and advisory warnings (amber) are separate lists. Published and archived versions are read-only.

## Accessibility measures
- Visible 3px focus ring on every control; skip link; landmarks (`header`, `nav`, `main`); `aria-current` on the active link; one `h1` per page, which also sets the tab title.
- Menus: `aria-expanded` / `aria-controls` on triggers, Escape closes and restores focus, Tab is trapped in the open drawer; dialogs are modal with focus moved in, trapped and restored; on phones dialogs become bottom sheets with a sticky action bar.
- Errors are announced (`role="alert"`) and tied to fields (`aria-describedby`, `aria-invalid`); status, lab / theory and validation severity are conveyed by text as well as colour.
- `prefers-reduced-motion` disables animation.
- Contrast was computed for the token pairs actually used: every text pair is >= 5.0:1 (body text 15.9:1, white on indigo 7.9:1, status text on status backgrounds 5.7-6.2:1), form-control borders 3.8:1 (>= 3:1).

## Verified in a real browser
During the redesign the screens were driven in headless Chrome against a throwaway database: every route for each role at 360, 390, 768, 1024 and 1440px (130 views) reported zero horizontal page overflow and zero inner horizontal scrollers (before the redesign: 12 views scrolled sideways at 390px and one overflowed the page at 1440px), plus menu, drawer, dialog, keyboard and focus checks. The scripts are not part of the repository; manual checking remains the final word.

## Honesty rules
No sample data ships in the UI. A screen whose backend does not exist shows "Not available yet" with its owner, requirement and milestone (Announcements, faculty self-service availability and the faculty workload page are still in that state).

## Shared list/table pattern (Milestone 2)
Every management screen is built from the same parts; `features/diya/TimeSlotsPage.jsx` is the reference.
- `hooks/useListQuery` - server-side paging, debounced search, filters, stale-response protection, step-back when a page empties, `reload()`.
- `components/data`: `DataTable` (loading skeleton, error + retry, empty vs "no results" states, dimmed refresh, stacked cards), `Pagination`, `TableToolbar` / `SearchBox` / `FilterSelect`.
- `components/ui`: `FormDialog` (focus starts on the first field), `CheckboxGroup`, `CheckboxField`, `ConfirmDialog`, `useToast`.
- Flow: add/edit in a dialog with client-side validation that mirrors the server; server errors map back onto the fields; delete asks for confirmation; success and failure are announced with a toast.
