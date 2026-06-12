# Finance Tracker Design System

The visual and motion language for `templates/index.html`. Every token and component
below corresponds to real CSS in that file (all tokens are CSS custom properties on
`:root`). Direction: **"warm ledger"** — paper-toned surfaces, ink text, a deep
fern-green money accent, hairline borders, tabular numerals, and crisp, fast motion.
The personality is a professional dashboard, so motion is brisk and restrained
(per Emil Kowalski's framework: high-frequency UI gets little or no animation;
modals and panes get fast `ease-out` entrances; exits are always faster than entries).

---

## 1. Design Tokens

### 1.1 Color — surfaces & ink

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F6F5F1` | App background (warm paper) |
| `--surface` | `#FFFFFF` | Cards, tables, modals |
| `--surface-sunken` | `#F4F2EC` | Table headers, inline-edit forms, meta chips |
| `--surface-hover` | `#FAF9F5` | Row / option hover |
| `--ink` | `#201E1A` | Primary text, dark fills |
| `--ink-2` | `#6B675D` | Secondary text |
| `--ink-3` | `#9C978A` | Tertiary text, hints, icon buttons at rest |
| `--line` | `#E6E3DA` | Hairline borders, row dividers |
| `--line-strong` | `#D3CFC2` | Input borders, emphasized dividers |
| `--header-bg` | `#23211C` | Top nav, floating action bar, total card |
| `--header-ink` | `#F6F5F1` | Text on dark surfaces |

### 1.2 Color — accent & semantic

| Token | Value | Use |
|---|---|---|
| `--accent` | `#0E7A5F` | Primary actions, links, focus, selection |
| `--accent-strong` | `#0A6450` | Primary hover |
| `--accent-soft` | `#E4F1EB` | Selected rows/cells, soft fills, focus ring |
| `--accent-soft-border` | `#C8E2D7` | Borders on soft accent fills |
| `--accent-on-dark` | `#57C29C` | Active nav underline on dark header |
| `--danger` / `--danger-strong` | `#C2402F` / `#A93425` | Destructive actions |
| `--danger-soft` / `--danger-soft-border` | `#FAEAE7` / `#F0CFC8` | Error boxes |
| `--success` / `--success-soft` / `--success-soft-border` | `#1E7F4F` / `#E7F4EC` / `#C4E5D2` | Credits, success states, "all settled" |
| `--warning-ink` / `--warning-soft` | `#8A6116` / `#F6ECD4` | Pending-review badge, pending rows |

### 1.3 Color — owners

Three owners, each with a solid (active tab), soft (badge bg), and ink (badge text)
variant. Kept maximally distinguishable: blue / magenta / gold.

| Owner | Solid | Soft | Ink |
|---|---|---|---|
| SHAN | `--owner-shan: #2563EB` | `#E4ECFC` | `#1D4ED8` |
| JANICE | `--owner-janice: #C72578` | `#FAE3EF` | `#A61E63` |
| JOINT | `--owner-joint: #B07D18` | `#F6ECD4` | `#8A6116` |

Category badge colors (`.cat-*`) and chart colors (`CAT_COLORS`) are unchanged —
category **names/keys must stay in sync with `app.py`** and the existing 14-hue
palette is already well differentiated.

### 1.4 Typography

System stack: `--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif`.

| Role | Size / weight | Notes |
|---|---|---|
| Page title | 24px / 700 | `letter-spacing: -0.02em` |
| Section title | 14px / 600 | `--ink-2` |
| Body / table | 13px / 400 | |
| Meta / sub | 12px / 400 | `--ink-2` |
| Micro labels | 10–11px / 600–700 | UPPERCASE, `letter-spacing: .04–.06em`, `--ink-3` |
| Amounts | inherit / 600–700 | always `font-variant-numeric: tabular-nums` |

All amounts render via `fmtAmount()`, dates via `fmtDate()` / `fmtDateObj()` /
`parseStatementDateLabel()` (non-negotiable display conventions).

### 1.5 Spacing

4px base scale, used as raw values in CSS: 4 / 8 / 12 / 16 / 20 / 24 / 32.
Card padding 24px (16px for `.card-sm`), table cells 10×14px (fixed — frozen-column
offsets in the Transactions table depend on it).

### 1.6 Radii

| Token | Value | Use |
|---|---|---|
| `--r-sm` | 6px | Tiny chips, inline inputs |
| `--r-btn` | 8px | Buttons, form inputs, selects |
| `--r-md` | 10px | Small cards, edit forms |
| `--r-lg` | 14px | Cards, panels, tables |
| `--r-pill` | 980px | Badges, tabs, pills, the action bar |

Buttons are rectangles (8px), not pills — pills are reserved for *labels/filters*
(badges, owner tabs, month pills) so shape encodes meaning.

### 1.7 Shadows

| Token | Value | Use |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(32,30,26,.05)` | Cards at rest |
| `--shadow-md` | `0 6px 20px rgba(32,30,26,.09)` | Detail pane card |
| `--shadow-lg` | `0 24px 64px rgba(32,30,26,.24)` | Modals |

### 1.8 Motion tokens

| Token | Value | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | All entrances and presses (strong custom ease-out — built-ins are too weak) |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` | On-screen movement (reserved) |
| `--dur-press` | `120ms` | Button press, view fade |
| `--dur-fast` | `150ms` | Hovers, inline forms, **all exits** |
| `--dur-base` | `200ms` | Pane entries, action bar |
| `--dur-modal` | `240ms` | Modal/overlay entries |

Rules: nothing over 300ms; exits always faster than entries (`--dur-fast`);
`ease-in` is never used; only `transform` and `opacity` are animated (plus
border/background colors on hover with plain `ease`).

---

## 2. Components

### 2.1 Buttons (`.btn`, `.btn-sm`, `.btn-outline`, `.btn-danger`, `.btn-success`)
- Solid accent fill, white text, `--r-btn`, `--shadow-sm`.
- Press feedback: `:active { transform: scale(0.97) }` over `--dur-press`.
- Hover darkens to `--accent-strong`, gated behind `@media (hover: hover) and (pointer: fine)`.
- Disabled: `--line-strong` fill, no transform.
- Icon buttons (`.btn-del`, `.bp-edit-btn`, `.sd-edit-btn`): tertiary ink at rest,
  colorize on hover (danger/accent), `:active` scale.

### 2.2 Badges
- `.cat-badge` — pill, 11px/600, per-category soft bg + dark text (14 fixed classes).
- `.owner-badge` — pill, 11px/700, owner soft bg + owner ink.
- `.stmt-ref` — 6px radius chip, accent-soft.
- `.pending-badge` — pill, warning-soft.
- `.settle-tab-badge` — count pill inside tabs; accent fill when tab active.

### 2.3 Cards
- `.card` / `.card-sm` / `.summary-card` / `.account-card` / `.settle-detail-card`:
  `--surface`, 1px `--line`, `--r-lg`/`--r-md`, `--shadow-sm`.
- `.summary-card.total` inverts to `--header-bg`.

### 2.4 Tables
- Wrapper `.table-wrap`: surface, `--r-lg`, hairline border, clipped corners.
- `th`: 11px uppercase micro label on `--surface-sunken`.
- Row dividers `--line`; row hover `--surface-hover` (hover-gated).
- Selected row `tr.tx-selected`: `--accent-soft` fill + 3px accent left bar.
- Frozen header/columns in Transactions keep their exact `left` offsets and
  `10px 14px` cell padding — **do not change cell padding there**.

### 2.5 Tabs & pills
- Nav links: dark header, `--accent-on-dark` underline for active.
- `.owner-tab`: pill; active fills with owner solid color.
- `.month-pill`: pill; active fills accent.
- `.settle-panel-tab`: underline tabs with accent indicator.
- Tab *switching* is instant (high-frequency action — no animation), only hover
  colors and `:active` scale transition.

### 2.6 Modals & overlays
- `.modal-overlay`: dimmed scrim `rgba(32,30,26,.45)`; fades in `--dur-base`,
  out `--dur-fast` (visibility-deferred so it stays mounted — pure CSS, JS still
  just toggles `.visible`).
- `.modal`: centered, `transform-origin` center (modals are exempt from
  origin-aware scaling), enters from `scale(0.96) translateY(8px)` → identity at
  `--dur-modal`, exits at `--dur-fast`. Never from `scale(0)`.
- `.review-overlay` (full-screen review): fades + rises 10px on enter, faster exit.
- `.action-bar` (floating bulk-actions): rises 12px from its bottom origin edge +
  fade; exit faster. Spatially consistent: always enters/exits toward the bottom.

### 2.7 Panels
- `#settle-detail-pane` is sticky; its `.settle-detail-card` content animates in
  from the right edge (`translateX(10px)` + fade, `--dur-base` `--ease-out`) via
  `@starting-style` every time a matrix cell is clicked — entry from its origin side.
- Selected matrix cell: `--accent-soft` highlight.

### 2.8 Forms
- Inputs/selects (`.step-select`, `.filter-select`, `.search-input`, `.review-input`,
  `.review-num-input`): `--r-btn`, `--line-strong` border; focus = accent border +
  3px `--accent-soft` ring.
- Inline edit forms (`.bp-edit-form`, `.sd-edit-form`): `--surface-sunken` panel,
  enters with fade + 3px drop (`140ms`); closing is instant (high-frequency).
- `accent-color: var(--accent)` on checkboxes.

### 2.9 Empty states & feedback
- `.no-data`, `.bp-hint`, `.settle-detail-empty`: tertiary ink, centered, generous padding.
- `.error-box` / `.success-box`: danger-soft / success-soft tints.
- `.spinner`: accent on `--line`, **0.6s** rotation (faster spin = faster perceived load).
- `.balance-summary.all-settled`: success-soft celebration state.

---

## 3. Motion Rules (what animates, how, why)

Justified by the frequency/purpose framework — every animation answers
"how often?" and "why?":

| Interaction | Frequency | Animation | Purpose / Emil rule |
|---|---|---|---|
| Button / pill / tab press | 100+ ×/day | `scale(0.97)`, 120ms ease-out | Feedback ("the UI heard you"); subtle 0.95–0.98 range |
| Tab/pill/checkbox *state* switch | 100+ ×/day | None (instant) | High-frequency → no animation, ever |
| Row selection highlight | 100+ ×/day | None (instant fill) | Same |
| Hover (buttons, rows, cells, nav) | tens ×/day | Color-only, 150ms `ease`, gated `@media (hover:hover) and (pointer:fine)` | Color change → `ease`; no false positives on touch |
| View switch (nav) | tens ×/day | Opacity-only 0→1, 120ms | Drastically reduced; prevents jarring swap; no movement |
| Modal open | occasional | Scrim fade 200ms + panel `scale(.96)+8px` rise, 240ms ease-out | Standard modal entrance; never `scale(0)`; centered origin |
| Modal close | occasional | 150ms (faster than open) | Exit faster than enter |
| Review overlay open/close | occasional | Fade + 10px rise 200/240ms; 150ms exit | Same pattern, full-screen |
| Settle detail pane content | occasional | Fade + `translateX(10px)` from right, 200ms ease-out, `@starting-style` | Spatial consistency: pane lives on the right, content enters from its edge |
| Inline edit form open | frequent-ish | Fade + 3px drop, 140ms; close instant | ≤150ms for frequent UI; asymmetric exit |
| Bulk action bar show/hide | frequent | Fade + 12px rise from bottom, 200ms in / 150ms out | Enters/exits from same edge; interruptible (transition, not keyframes) |
| Upload dropzone dragover | rare | Border/background color, 200ms | State indication |
| Spinner | during loads | 0.6s linear rotation | Perceived performance (faster spin feels faster) |
| Chevrons (accordions) | frequent | 150ms rotate | Prevents jarring flip |

Implementation constraints:
- **Transitions, not keyframes**, for everything interruptible (modals, action bar,
  pane) — they retarget smoothly when toggled rapidly.
- Only `transform`/`opacity` (+ colors on hover). Never `transition: all`.
- Entrances use `@starting-style` (no JS mount-state hacks); browsers without it
  simply skip the entrance — fully functional fallback.
- No stagger animations: list contents are data the user scans tens of times a day;
  decoration would slow comprehension.

### `prefers-reduced-motion: reduce`
Reduced, not removed: all **movement** is stripped (modal/pane/action-bar/form
translates and scales, press scaling, chevron rotation transitions) while
**opacity and color** transitions are kept to aid comprehension. The spinner is
retained as essential progress feedback.

---

## 4. Accessibility
- Hover effects gated behind `@media (hover: hover) and (pointer: fine)`.
- `:focus-visible` rings (2px accent, offset 2px) on buttons, tabs, and pills.
- `prefers-reduced-motion` fallbacks as above.
- Owner colors chosen for at-a-glance distinguishability (blue/magenta/gold) with
  ≥4.5:1 text contrast in badge form.
