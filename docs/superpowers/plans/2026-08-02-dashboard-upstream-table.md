# Dashboard Upstream Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing spending workspace as a compact upstream-inspired category table without adding budget or projection data.

**Architecture:** Retain the existing Jinja `category_row` macro and `GroupedSpendingResponse` input. The template continues to render Income first and Expenses second; CSS changes only the spending-workspace shell, section headings, rows, columns, meter, and parent/child treatment to make the existing data read as a dense financial table.

**Tech Stack:** Jinja2, CSS, pytest, Taskfile.

## Global Constraints

- Reuse the existing actual and share fields; projected/budget columns are out of scope.
- Keep the single scrollable report with Income before Expenses, descending parent roll-ups, zero-spend omission, and native category disclosure.
- Preserve empty and unavailable states and the existing dashboard route/service boundary.

---

### Task 1: Add a regression check for the compact table structure

**Files:**

- Modify/Test: `tests/test_dashboard.py`

**Interfaces:**

- Consumes: the grouped category fixture in `test_dashboard_renders_parent_categories_and_mascot`.
- Produces: an assertion that the rendered category report has table-specific section and column hooks.

- [ ] **Step 1: Write the failing assertion**

Add these expectations to the dashboard rendering test:

```python
assert 'class="category-table"' in response.text
assert 'class="category-table__columns"' in response.text
assert 'class="category-section__heading"' in response.text
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: FAIL because the compact-table container and column header do not yet exist.

### Task 2: Render and style the compact table

**Files:**

- Modify: `src/lunchmoney_mcp/app/templates/dashboard.html`
- Modify: `src/lunchmoney_mcp/app/static/dashboard.css`
- Test: `tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

**Interfaces:**

- Consumes: `category_row(category, category_total, swatch_index)` and `GroupedSpendingResponse` fields already rendered by the template.
- Produces: `.category-table`, `.category-table__columns`, compact `.category-item` rows, and category-color meter variables shared with nested children.

- [ ] **Step 1: Add semantic table hooks**

Wrap the section output and add a single column header:

```html
<div class="category-table">
    <div class="category-table__columns" aria-hidden="true">
        <span>Actual</span><span>Share</span>
    </div>
    <!-- Income and Expenses sections -->
</div>
```

- [ ] **Step 2: Apply dense table styling**

Use the existing four-column grid for every parent and child row. Tighten row height and section spacing; give parent rows a stronger weight, children a muted label, and meters a shared per-category color. Keep the track near-black and preserve sufficient contrast for actual/share values.

- [ ] **Step 3: Run the targeted test to verify it passes**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: PASS.

### Task 3: Verify the redesign

**Files:**

- Modify: `docs/CHECKLIST.md`

**Interfaces:**

- Consumes: passing dashboard and static checks.
- Produces: completed dashboard interaction entry only after all project checks pass.

- [ ] **Step 1: Run dashboard tests**

Run: `task test -- tests/test_dashboard.py`

Expected: PASS.

- [ ] **Step 2: Run formatter and static checks**

Run: `task fix && task check`

Expected: each command exits 0.

- [ ] **Step 3: Run the full suite**

Run: `task test`

Expected: PASS, or report unrelated failures without changing unrelated code.

- [ ] **Step 4: Commit**

Commit the reviewed implementation with `✨ (dashboard): adopt compact category table`.
