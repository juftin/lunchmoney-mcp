# Design: Lightweight SPA Dashboard

> **Status**: Proposed
> **Author**: Agent
> **Date**: 2026-08-03

## Table of Contents

1. [Problem](#1-problem)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [Architecture](#3-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Component Design](#5-component-design)
6. [Data Flow](#6-data-flow)
7. [File Manifest](#7-file-manifest)
8. [Router Design](#8-router-design)
9. [Client-Side State](#9-client-side-state)
10. [CSS Strategy](#10-css-strategy)
11. [Responsive Breakpoints](#11-responsive-breakpoints)
12. [Accessibility](#12-accessibility)
13. [Error Handling](#13-error-handling)
14. [Testing Strategy](#14-testing-strategy)
15. [Implementation Phases](#15-implementation-phases)
16. [Rollback Plan](#16-rollback-plan)

---

## 1. Problem

The current dashboard is a **server-rendered Jinja2 template** served at `GET /`. Every interaction — navigating months, refreshing data — requires a full page reload. The frontend consists of:

- `dashboard.html` — 511-line Jinja2 template with embedded macros and server-injected context
- `dashboard.css` — 860 lines of custom CSS built on Tabler UI (~200KB vendored framework)
- `dashboard.js` — 23 lines of vanilla JS for tab switching only
- `services/dashboard.py` — 224-line data composition calling 7 async operations in parallel

**Problems**:

1. **Full page reloads on every interaction** — period navigation destroys client state, re-downloads all assets, flashes the page
2. **Heavy CSS dependency** — Tabler is 200KB for a dashboard that uses ~10% of it
3. **No client-side interactivity** — no search, no keyboard shortcuts, no live refresh
4. **Tight coupling** — server template and service are wholly owned by the dashboard; no partial reuse

## 2. Goals & Non-Goals

### Goals

- Eliminate full-page reloads for period navigation and tab switching
- Reduce CSS from 200KB (Tabler) + 860 lines custom → 20KB (Pico) + ~200 lines custom
- Add client-side search, keyboard shortcuts, live polling, smooth transitions
- Keep zero build pipeline — all dependencies via CDN `<link>` / `<script>` tags
- Preserve the visual design — no pixel-level regressions
- Reuse `services/dashboard.py` as-is — no changes to the data composition layer
- Support deep linking — period URLs are bookmarkable and shareable

### Non-Goals

- No JavaScript framework (React, Vue, Svelte)
- No npm/Node.js build step
- No new Python dependencies
- No new REST API endpoints (unless a gap is found)
- No changes to the auth model
- No changes to other routers or services
- No real-time WebSocket push (polling is sufficient)

## 3. Architecture

### Current

```
Browser                    FastAPI
  │                          │
  │  GET /?period=2026-07    │
  │  ──────────────────────► │  fetch_dashboard_data() → 7 parallel async calls
  │                          │  Jinja2 renders full page → HTMLResponse
  │  ◄────────────────────── │
  │                          │
  │  (click next month)      │
  │  GET /?period=2026-08    │
  │  ──────────────────────► │  ...full page render again...
  │  ◄────────────────────── │
```

### Target

```
Browser                                              FastAPI
  │                                                    │
  │  GET /?period=2026-07                               │
  │  ────────────────────────────────────────────────► │  fetch_dashboard_data()
  │  ◄──────────────────────────────────────────────── │  Jinja2 → full HTMLResponse
  │                                                    │
  │  (click next month: HTMX intercepts click)          │
  │  GET /?period=2026-08     HX-Request: true          │
  │  ────────────────────────────────────────────────► │  fetch_dashboard_data()
  │  ◄──────────────────────────────────────────────── │  Jinja2 → cockpit_content.html (partial)
  │  (Idiomorph morphs DOM, URL updates, chart re-draws)│
  │                                                    │
  │  (live polling every 60s)                           │
  │  GET /sync/status          HX-Request: true         │
  │  ────────────────────────────────────────────────► │  get_scheduled_sync_status()
  │  ◄────────────────────────── (tiny HTML fragment)   │
```

**Key insight**: No new API endpoints. `GET /` detects the `HX-Request` header and returns either the full page or a partial depending on context.

## 4. Technology Stack

| Layer                  | Tool                                                     | Size (CDN) | Role                                                                  |
| :--------------------- | :------------------------------------------------------- | :--------- | :-------------------------------------------------------------------- |
| **CSS Framework**      | [Pico CSS](https://picocss.com)                          | ~20KB      | Dark theme, typography, `<dialog>`, `<details>`, form/button defaults |
| **HTML Over the Wire** | [HTMX](https://htmx.org)                                 | ~14KB      | Partial-page swaps, push-url, polling, AJAX navigation                |
| **DOM Morphing**       | [Idiomorph](https://github.com/bigskysoftware/idiomorph) | ~5KB       | Smooth transitions on DOM swaps (HTMX extension)                      |
| **Client State**       | [Alpine.js](https://alpinejs.dev)                        | ~15KB      | Tab state, search filter, keyboard shortcuts, toasts, chart lifecycle |
| **Charts**             | [Frappe Charts](https://frappe.io/charts)                | ~20KB      | Donut chart for category spending breakdown                           |
| **Icons**              | [Lucide](https://lucide.dev)                             | inline SVG | Period nav arrows, empty-state icon                                   |

**Total payload**: ~80KB. All served via CDN `<script>`/`<link>` tags. Zero build step.

### Why This Stack

| Requirement               | Why Not Vanilla JS                     | Why Not React/Vue/Svelte                                      |
| :------------------------ | :------------------------------------- | :------------------------------------------------------------ |
| Period nav without reload | Manual fetch + DOM render (~400 lines) | Framework boilerplate, build pipeline, duplicate server logic |
| Smooth transitions        | Manual FLIP animations                 | Framework-specific transition APIs                            |
| Search/filter             | Manual event binding + DOM walk        | Framework component state                                     |
| Zero build                | Yes                                    | No — requires bundler                                         |
| Reuse server templates    | Must reimplement in JS                 | Must reimplement in JS                                        |

HTMX + Alpine is the only stack that satisfies all constraints: **no build step, server-rendered templates, declarative interactivity, and extensibility** — a new dashboard section is just a new Jinja2 partial + one `hx-get` attribute.

## 5. Component Design

### 5.1 Server Components (unchanged)

```
src/lunchmoney_mcp/services/dashboard.py
  └── fetch_dashboard_data(db, client, period_start, transaction_limit)
      └── asyncio.gather(
            sync_metadata   → db.get_sync_metadata("transactions")
            accounts        → fetch_accounts(db)
            budget_summary  → fetch_account_summary(client, start, end)
            budget_settings → fetch_budget_settings(client)
            category_spend  → fetch_category_spending(db, start, end)
            transactions    → fetch_recent_transactions(db, limit, start, end)
            scheduled_sync  → get_scheduled_sync_status(db)
          )
      → DashboardData dataclass (12 fields)
```

This function is **untouched**. It continues to be the single source of truth for dashboard data.

### 5.2 Template Components

```
templates/dashboard.html                  ← Full page (initial load, direct URL visits)
  ├── <head> CDN links
  ├── <body x-data="dashboard">
  │   ├── .cockpit-header
  │   │   ├── .brand (logo + title)
  │   │   ├── .period-control (prev/next month buttons)
  │   │   └── .header-status (live-dot + sync timestamp, hx-polling)
  │   ├── <main id="dashboard-content">
  │   │   └── {% include "partials/cockpit_content.html" %}
  │   └── <dialog id="api-key-dialog"> (API key entry modal)
  │
  └── partials/cockpit_content.html        ← Content area (HTMX partial swap target)
      ├── .dashboard-alert (partial data banner, if unavailable_sections)
      ├── .left-rail
      │   ├── .welcome + .panel-switcher (Alpine x-show tabs)
      │   ├── #accounts-panel  (account groups + net worth)
      │   ├── #summary-panel   (period income/expense/savings/budget)
      │   └── #activity-panel  (recent transactions + sync status)
      └── .spending-workspace
          ├── .workspace-heading (month label + income/expense totals)
          ├── .flow-band (income vs expense bar)
          ├── .category-table → .category-explorer
          │   ├── Income section → category items (expandable parents + children)
          │   └── Expenses section → category items
          └── <script id="chart-data" type="application/json"> (Frappe data)
```

## 6. Data Flow

### 6.1 Initial Page Load

```
Browser                          FastAPI                                 Services
  │                                │                                       │
  │  GET /                         │                                       │
  │  (no HX-Request header)        │                                       │
  │  ──────────────────────────►   │  fetch_dashboard_data()               │
  │                                │  ──────────────────────────────────► │  7 parallel async calls
  │                                │  ◄────────────────────────────────── │  DashboardData
  │                                │                                       │
  │  ◄──────────────────────────   │  Jinja2 renders dashboard.html       │
  │                                │  (includes cockpit_content.html)      │
  │                                │                                       │
  │  Alpine.init()                 │                                       │
  │  Frappe.initChart()            │                                       │
```

### 6.2 Period Navigation (HTMX)

```
Browser                          FastAPI                                 Services
  │                                │                                       │
  │  (user clicks ">" arrow)       │                                       │
  │  HTMX intercepts click          │                                       │
  │  │                               │                                       │
  │  GET /?period=2026-08-01        │                                       │
  │  HX-Request: true               │                                       │
  │  HX-Target: #dashboard-content  │                                       │
  │  ──────────────────────────►   │  fetch_dashboard_data(period_start)   │
  │                                │  ──────────────────────────────────► │  7 parallel async calls
  │                                │  ◄────────────────────────────────── │  DashboardData
  │                                │                                       │
  │  ◄──────────────────────────   │  Jinja2 renders cockpit_content.html  │
  │                                │                                       │
  │  Idiomorph morphs DOM          │                                       │
  │  HTMX pushes URL state         │                                       │
  │  htmx:afterSettle triggers:    │                                       │
  │    Alpine re-initialize tabs   │                                       │
  │    Frappe re-initialize chart  │                                       │
```

### 6.3 Live Polling

```
Browser                          FastAPI
  │                                │
  │  (every 60s automatically)     │
  │  GET /sync/status              │
  │  HX-Request: true              │
  │  ──────────────────────────►   │  get_scheduled_sync_status(db)
  │  ◄──────────────────────────   │  ScheduledSyncStatus | None
  │                                │
  │  HTMX swaps sync-status span   │
```

## 7. File Manifest

### 7.1 New Files

| File                                      | Lines (est.) | Purpose                                                                                            |
| :---------------------------------------- | :----------- | :------------------------------------------------------------------------------------------------- |
| `templates/dashboard.html`                | ~200         | Full-page template with Pico classes, CDN links, Alpine root, structural layout                    |
| `templates/partials/cockpit_content.html` | ~150         | Content area partial — extracted from old dashboard.html lines 169-508                             |
| `static/dashboard.css`                    | ~200         | Dashboard-specific layout only (grid, category tree, account groups, flow band)                    |
| `static/dashboard.js`                     | ~80          | Alpine.js component — tab state, search, collapse-all, keyboard shortcuts, chart init, toast queue |
| `docs/DESIGN_DASHBOARD_SPA.md`            | this file    | Design document                                                                                    |

### 7.2 Modified Files

| File                      | Change                                                                                                    |
| :------------------------ | :-------------------------------------------------------------------------------------------------------- |
| `routers/dashboard.py`    | Add `HX-Request` header detection → return partial or full template. Add Pico CDN URL to template context |
| `tests/test_dashboard.py` | Update assertions for new template structure and HTMX partial responses                                   |

### 7.3 Removed Files

| File                                  | Reason                                 |
| :------------------------------------ | :------------------------------------- |
| `static/vendor/tabler/tabler.min.css` | Replaced by Pico CSS (~20KB vs ~200KB) |
| `static/dashboard.js` (old)           | Replaced by Alpine component           |
| `static/dashboard.css` (old)          | Replaced by Pico-based rewrite         |

### 7.4 Untouched Files

| File                                                                                            | Reason                                                                        |
| :---------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------- |
| `services/dashboard.py`                                                                         | No changes — `fetch_dashboard_data()` reused verbatim                         |
| `services/accounts.py`, `spending.py`, `budgets.py`, `summary.py`, `sync.py`, `transactions.py` | Unchanged                                                                     |
| `routers/accounts.py`, `spending.py`, `budgets.py`, `summary.py`, `sync.py`, `transactions.py`  | Unchanged                                                                     |
| `app/main.py`                                                                                   | Unchanged — static mount, router registration, auth middleware all work as-is |
| `app/auth.py`                                                                                   | Unchanged — API key auth still guards `GET /` and all REST routes             |
| `static/mascot.png`                                                                             | Unchanged                                                                     |

## 8. Router Design

### `routers/dashboard.py`

```python
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    db: Annotated[LunchMoneyDatabase, Depends(get_database)],
    client: Annotated[LunchMoneyApp, Depends(get_lunchmoney_app)],
    period: Annotated[datetime.date | None, Query()] = None,
) -> HTMLResponse:
    """Render the authenticated Lunch Money dashboard."""
    data = await fetch_dashboard_data(db=db, client=client, period_start=period)
    context = {
        "request": request,
        "dashboard": data,
    }

    if request.headers.get("HX-Request"):
        # HTMX: return content-area partial for in-place swap
        return templates.TemplateResponse(
            "partials/cockpit_content.html", context
        )

    # Full-page: return complete document
    return templates.TemplateResponse("dashboard.html", context)
```

**Key design decisions**:

- **One endpoint, two response shapes** — `HX-Request` is the canonical HTMX header; its presence signals a partial swap. This avoids creating new endpoints and keeps URL structure unchanged.
- **`hx-push-url="true"`** on period nav links ensures the browser URL updates (`/?period=2026-08-01`), making period state bookmarkable and shareable.
- **No new dependencies** — `HX-Request` is a simple string check; no middleware or decorator needed.

## 9. Client-Side State

All client state lives in a single Alpine.js component bound to `<body>`.

### `Alpine.data('dashboard', ...)`

```js
{
  // === Tab state ===
  activeTab: 'accounts',        // 'accounts' | 'summary' | 'activity'

  // === Search ===
  searchQuery: '',               // filters category tree in real-time

  // === Detail toggle ===
  allExpanded: false,            // collapse/expand all <details> groups

  // === API key ===
  apiKey: localStorage.getItem('lm_api_key') || '',
  showApiKeyDialog: false,

  // === Toast queue ===
  toasts: [],                    // { id, message, type, ttl }

  // === Methods ===
  setTab(tab),
  onKeydown(event),              // keyboard shortcut dispatcher
  toggleAllDetails(),
  filterCategories(),            // reactive filter for category tree
  initChart(),                   // Frappe Charts initialization
  prevPeriod(),                  // dispatch custom event for HTMX
  nextPeriod(),
  submitApiKey(),                // store in localStorage, retry failed requests
  addToast(message, type),
  dismissToast(id),
}
```

### HTMX ↔ Alpine Integration

```
[User clicks next month button]
  │
  ├── Alpine @click → $dispatch('periodChange', { period: nextStart })
  │
  ├── HTMX hx-trigger="periodChange" → issues GET /?period=...
  │
  ├── Server returns cockpit_content.html partial
  │
  ├── Idiomorph morphs #dashboard-content DOM (smooth transition)
  │
  └── HTMX fires htmx:afterSettle
        ├── Alpine re-evaluates x-data bindings on new DOM
        ├── Alpine $watch triggers chart re-init
        └── Scroll position preserved (Idiomorph handles this)
```

### Keyboard Shortcuts

| Key      | Action                     | Condition    |
| :------- | :------------------------- | :----------- |
| `1`      | Switch to Accounts tab     | Not in input |
| `2`      | Switch to Period tab       | Not in input |
| `3`      | Switch to Activity tab     | Not in input |
| `j`      | Previous month             | Not in input |
| `k`      | Next month                 | Not in input |
| `/`      | Focus search input         | Not in input |
| `Escape` | Clear search, close dialog | Anywhere     |

Shortcuts are scoped: if focus is on `<input>`, `<textarea>`, `<select>`, or `[contenteditable]`, shortcuts are suppressed.

## 10. CSS Strategy

### What Pico CSS Replaces

| Former Custom CSS (lines)                | Replaced By                                           |
| :--------------------------------------- | :---------------------------------------------------- |
| `:root` color tokens (1-20)              | Pico dark theme CSS variables via `data-theme="dark"` |
| `*` box-sizing + `body` defaults (22-31) | Pico reset                                            |
| `button`, `a` font inheritance (33-40)   | Pico defaults                                         |
| Tabler vendor CSS (200KB)                | Pico CSS (20KB)                                       |
| Alert/dialog styles (172-185)            | Pico `<article>` + `<dialog>`                         |
| Empty-state typography (729-755)         | Pico typography + custom layout                       |

### What Stays Custom (~200 lines)

All dashboard-specific layout — Pico is a classless CSS framework and doesn't provide grid layouts, custom component styling, or financial UI patterns.

```
.cockpit                 gradient background + padding
.cockpit-header          3-column grid (brand | period-control | status)
.cockpit-layout          2-column grid, viewport-height constraint
.brand, .brand-mascot    logo + text
.period-control          segmented button group with borders
.live-dot                animated status indicator (green dot + glow)
.panel-switcher          tab bar with gold active-state border
.rail-panel              flex column, overflow scroll, [hidden] toggle
.account-tree            nested details/summary with indented list
.net-worth               footer bar in accounts panel
.period-summary          definition-list grid layout
.activity-list           transaction items with payee/date/amount
.budget-status           footer bar in summary panel
.sync-status             footer bar in activity panel
.spending-workspace      flex column layout
.flow-band               income vs expense horizontal bar
.category-table          grid-based category explorer
.category-item           4-column grid rows with meter bars
.category-swatch         colored dot indicators (6-tone palette)
.category-children       nested child rows with tree-line connectors
.category-disclosure     expand/collapse chevron animation
.empty-state             centered empty/loading states
.skip-link               accessibility skip-to-content link
.toast-container         fixed notification area (new)
.api-key-dialog          API key entry modal overlay (new)
@responsive              breakpoints at 900px and 560px
```

### Color Palette (convenience aliases for custom CSS)

```css
:root {
    --gold: #efb20e; /* active tab, brand accents, category names */
    --green: #32cf82; /* positive amounts, status dot */
    --coral: #ff5c6c; /* negative amounts */
    --blue: #5f7ce8; /* category swatch 3 */
    --purple: #a36ddd; /* category swatch 4 */
    --teal: #1fb6a5; /* category swatch 5 */
}
```

These are convenience aliases layered on top of Pico's CSS variables. They are not design tokens — Pico owns the design token layer.

## 11. Responsive Breakpoints

| Width   | Layout                                                                         |
| :------ | :----------------------------------------------------------------------------- |
| > 900px | Two-column grid (left rail + workspace), `overflow: hidden` on body            |
| ≤ 900px | Single-column stack, `overflow: auto` on body, panel-switcher spans full width |
| ≤ 560px | Compact: tighter padding, smaller fonts, category meter column hidden          |

All breakpoints are pure CSS `@media` queries. No JavaScript resize handling needed — Pico handles fluid typography, and the custom CSS handles grid reflows.

## 12. Accessibility

| Feature           | Implementation                                                                                                            |
| :---------------- | :------------------------------------------------------------------------------------------------------------------------ |
| Skip link         | `.skip-link` — `position: fixed`, revealed on focus, targets `#dashboard-content`                                         |
| Tab panel roles   | `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls`, `aria-labelledby`                    |
| Period nav labels | `aria-label="Previous month"` / `"Next month"` on period nav buttons                                                      |
| Live region       | Dashboard alert uses `role="status"` for partial-data announcements                                                       |
| Keyboard nav      | All interactive elements are focusable. Keyboard shortcuts are additive, not replacements for native tab/arrow navigation |
| Color             | Positive/negative amounts use color **and** `+`/`-` sign prefix. Category swatches are supplementary to text labels       |
| Motion            | `prefers-reduced-motion` respected for morphed transitions and loading spinners                                           |
| HTMX              | `hx-target` swaps preserve focus where possible. Idiomorph preserves scroll position                                      |

## 13. Error Handling

### API Key

| Scenario                                           | Behavior                                                                                |
| :------------------------------------------------- | :-------------------------------------------------------------------------------------- |
| Key not configured on server, none in localStorage | API calls pass through (auth middleware allows un-keyed requests)                       |
| Key configured on server, missing in localStorage  | API calls return 401 → dialog shown, user enters key → stored in `localStorage` → retry |
| Key configured on server, wrong in localStorage    | API calls return 401 → dialog shown with error message → user re-enters                 |
| Key configured, correct, stored                    | Normal operation, no dialog                                                             |

### Section Failures (Graceful Degradation)

The server's `fetch_dashboard_data()` already wraps each section in `_capture()` and populates `unavailable_sections`. The template renders:

```html
{% if dashboard.unavailable_sections %}
<section class="dashboard-alert" role="status">
    <strong>Partial data</strong>
    <span
        >{{ dashboard.unavailable_sections | join(', ') }} will return on the
        next refresh.</span
    >
</section>
{% endif %}
```

Individual sections fall back to their `.empty-state` markup when data is `None`.

### Network Errors (Client-Side)

HTMX fires `htmx:responseError` on non-2xx responses. Alpine listens for this:

```js
document.body.addEventListener("htmx:responseError", (e) => {
    if (e.detail.xhr.status === 401) {
        this.showApiKeyDialog = true;
    } else {
        this.addToast(`Could not load ${e.detail.target.id}`, "error");
    }
});
```

### Loading States

HTMX provides `hx-indicator` — a CSS class applied to an element during the request. The indicator is shown on the element being swapped:

```html
<div hx-get="/..." hx-indicator="#loading-spinner">
    <!-- content -->
</div>
<div id="loading-spinner" class="htmx-indicator">
    <!-- spinner shown during request, hidden otherwise -->
</div>
```

Pico CSS provides `aria-busy="true"` styling for loading states.

## 14. Testing Strategy

### Backend (pytest)

| Test                                       | Description                                                               |
| :----------------------------------------- | :------------------------------------------------------------------------ |
| `test_dashboard_full_page`                 | `GET /` returns 200 with complete HTML document                           |
| `test_dashboard_htmx_partial`              | `GET /` with `HX-Request: true` header returns content-area partial only  |
| `test_dashboard_period_nav`                | `GET /?period=2026-01-01` returns correct period data in template context |
| `test_dashboard_unavailable_sections`      | Partial data banner rendered when 3 of 7 sections fail                    |
| `test_dashboard_auth`                      | `GET /` without API key returns 401 when key configured                   |
| `test_dashboard_empty_state`               | Empty-state markup rendered when accounts/transactions/spending is None   |
| `test_dashboard_html_contains_cdn_links`   | Response includes Pico, HTMX, Alpine, Frappe CDN URLs                     |
| `test_dashboard_html_contains_alpine_root` | Response includes `x-data="dashboard"` on `<body>`                        |

### Frontend (manual verification, future: Playwright)

| Test               | Description                                                                       |
| :----------------- | :-------------------------------------------------------------------------------- |
| Tab switching      | Click each tab, verify panel visibility, aria-selected updates                    |
| Period navigation  | Click prev/next month, verify URL updates, content swaps smoothly                 |
| Live polling       | Verify sync status dot updates within 60s                                         |
| Search filter      | Type in search, verify category tree filters in real time                         |
| Collapse all       | Click toggle, verify all `<details>` open/close                                   |
| Keyboard shortcuts | Press 1/2/3, j/k, /, Escape — verify actions                                      |
| API key flow       | Clear localStorage, refresh — verify dialog appears. Enter key — verify dismissed |
| Responsive         | Resize to 900px and 560px breakpoints, verify layout reflows                      |
| Chart rendering    | Verify donut chart renders on load and re-renders after period nav                |
| Empty states       | Verify empty-state copy when no accounts, no transactions, no spending            |

## 15. Implementation Phases

### Phase 1 — Core Rewrite

**Goal**: Working dashboard with Pico + HTMX + Alpine. No new features.

| Step | Files                                                             | Verification                                                         |
| :--- | :---------------------------------------------------------------- | :------------------------------------------------------------------- |
| 1.1  | Write `dashboard.css` (Pico-based, ~200 lines)                    | Visual parity with current dashboard at 1920px, 900px, 560px         |
| 1.2  | Extract `partials/cockpit_content.html` from old `dashboard.html` | Template renders without errors with test context                    |
| 1.3  | Write `dashboard.html` (Pico classes, CDN links, Alpine root)     | Page loads with correct structure                                    |
| 1.4  | Write Alpine component (`dashboard.js`) — tab switching only      | Tab clicks switch panels, no page reload                             |
| 1.5  | Update `routers/dashboard.py` — add `HX-Request` conditional      | `GET /` returns full page; `GET /` with `HX-Request` returns partial |
| 1.6  | Wire HTMX period nav: `hx-get`, `hx-target`, `hx-push-url`        | Click next month → URL updates → content swaps → no full reload      |
| 1.7  | Remove Tabler CSS, old `dashboard.css`, old `dashboard.js`        | No import errors, no missing styles                                  |
| 1.8  | Run `task fix && task lint && task check && task test`            | All pass                                                             |

### Phase 2 — Polish

**Goal**: Animations, charts, live refresh, error handling.

| Step | Files                                                                   | Verification                                             |
| :--- | :---------------------------------------------------------------------- | :------------------------------------------------------- |
| 2.1  | Add Idiomorph CDN + `hx-swap="morph:innerHTML"`                         | Period nav transitions are smooth, scroll preserved      |
| 2.2  | Add Frappe Charts CDN + `chart-data` JSON inline + Alpine `initChart()` | Donut chart renders on load, re-renders after period nav |
| 2.3  | Add live polling: `hx-trigger="every 60s"` on sync status               | Sync dot updates within 60s                              |
| 2.4  | Add API key dialog (Pico `<dialog>` + Alpine)                           | 401 → dialog → enter key → stored → retry                |
| 2.5  | Add toast system (Alpine)                                               | Error toasts appear on network failures                  |
| 2.6  | Add loading indicators (`hx-indicator`, `aria-busy`)                    | Spinner shown during swaps                               |

### Phase 3 — Interactivity

**Goal**: Search, keyboard, collapse-all, relative timestamps.

| Step | Files                                                       | Verification                                                |
| :--- | :---------------------------------------------------------- | :---------------------------------------------------------- |
| 3.1  | Add category search filter (Alpine `x-model` + filter)      | Typing filters tree, clearing restores                      |
| 3.2  | Add collapse-all toggle (Alpine `toggleAllDetails()`)       | Button toggles all `<details>` open/close                   |
| 3.3  | Add keyboard shortcuts (Alpine `onKeydown()`)               | 1/2/3 for tabs, j/k for months, / for search, Esc for clear |
| 3.4  | Add relative timestamps (custom Alpine directive or filter) | "Synced 2 hours ago" instead of absolute datetime           |

## 16. Rollback Plan

1. **Revert `routers/dashboard.py`** to serve old `dashboard.html` template
2. **Revert `templates/dashboard.html`** to the Jinja2 version (from git)
3. **Restore** old `dashboard.css`, `dashboard.js`, `vendor/tabler/tabler.min.css` (from git)
4. **Delete** new files: `dashboard.css`, `dashboard.js`, `dashboard.html`, `partials/cockpit_content.html`

The service layer (`services/dashboard.py`) is never modified, so there is no data-level rollback risk.

---

## Appendix A: CDN URLs

| Tool          | URL                                                                           |
| :------------ | :---------------------------------------------------------------------------- |
| Pico CSS      | `https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css`               |
| HTMX          | `https://unpkg.com/htmx.org@2/dist/htmx.min.js`                               |
| Idiomorph     | `https://unpkg.com/idiomorph/dist/idiomorph-ext.min.js`                       |
| Alpine.js     | `https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js`                     |
| Frappe Charts | `https://cdn.jsdelivr.net/npm/frappe-charts@1/dist/frappe-charts.min.iife.js` |

## Appendix B: Template Context

The Jinja2 context passed to both `dashboard.html` and `partials/cockpit_content.html`:

```python
{
    "request": request,          # FastAPI Request (required by Jinja2Templates)
    "dashboard": DashboardData(  # from services/dashboard.py
        period_start,
        period_end,
        previous_period_start,
        next_period_start,
        transaction_last_synced_at,
        accounts,                # AccountsSummary | None
        budget_summary,          # SummaryResponseObject | None
        budget_settings,         # BudgetSettingsResponseObject | None
        category_spending,       # GroupedSpendingResponse | None
        transactions,            # list[TransactionInfo] | None
        scheduled_sync,          # ScheduledSyncStatus | None
        unavailable_sections,    # tuple[str, ...]
    ),
}
```

## Appendix C: Frappe Charts Data Format

The server renders spending data as JSON inline in the partial template:

```html
<script id="chart-data" type="application/json">
    {
      "labels": ["Groceries", "Dining Out", "Entertainment", ...],
      "datasets": [{ "values": [450.00, 320.00, 180.00, ...] }]
    }
</script>
<div id="category-donut"></div>
```

Alpine `initChart()` parses this and initializes Frappe:

```js
initChart() {
  const el = document.getElementById('chart-data');
  if (!el) return;
  const data = JSON.parse(el.textContent);
  new frappe.Chart('#category-donut', {
    data: data,
    type: 'percentage',
    height: 240,
    colors: ['#32cf82', '#efb20e', '#ff5c6c', '#5f7ce8', '#a36ddd', '#1fb6a5'],
  });
}
```
