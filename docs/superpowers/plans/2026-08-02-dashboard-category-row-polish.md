# Dashboard Category-row Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make category groups and child rows easier to scan while correcting negative income-share display artifacts.

**Architecture:** Keep the existing Jinja category-row macro and server-rendered dashboard. Adjust its local presentation markup for a non-clipped parent label, calculate shares with an absolute section denominator, and use CSS to align child meters with parent meters while replacing the heavy tree connector with a short guide.

**Tech Stack:** Jinja2, CSS, pytest, Taskfile.

## Global Constraints

- Preserve the current dashboard layout, monthly route, scrollable report, data service, sorting, and zero-spend omission.
- Do not change transaction classification or aggregate service totals.
- Do not add SPA infrastructure, filters, budgets, or projected columns.

---

### Task 1: Cover the row-polish rendering contract

**Files:**

- Modify/Test: `tests/test_dashboard.py`

**Interfaces:**

- Consumes: the existing dashboard fixture and static `dashboard.css` endpoint.
- Produces: regression coverage for absolute income shares, an isolated parent-label truncation hook, and the short child-row guide.

- [x] **Step 1: Write the failing assertions**

Set the fixture's Salary amount and `total_income` to `-100`, then assert the
rendered share is positive. Add checks for the parent text hook and child guide:

```python
data.category_spending.total_income = -100
# Salary's total_amount is -100
assert "<em>100.0%</em>" in response.text
assert "<em>-100.0%</em>" not in response.text
assert 'class="category-name__label"' in response.text
assert ".category-child__name::before" in css_response.text
```

- [x] **Step 2: Run the focused test to verify it fails**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: FAIL because the current template divides an absolute amount by a
negative income total and does not expose the label hook.

### Task 2: Polish group and child rows

**Files:**

- Modify: `src/lunchmoney_mcp/app/templates/dashboard.html`
- Modify: `src/lunchmoney_mcp/app/static/dashboard.css`
- Test: `tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

**Interfaces:**

- Consumes: `category_row(category, category_total, swatch_index)`.
- Produces: `.category-name__label` and a consistent four-column child-row grid.

- [x] **Step 1: Make the share denominator absolute**

In the macro, create an absolute denominator before calculating parent and
child percentages:

```jinja
{% set section_total = category_total | abs %}
{% set percent = ((category.total_amount | abs / section_total) * 100) | round %}
```

Use `section_total` for `child_percent` as well. The call sites already pass
`1` when a section total is zero.

- [x] **Step 2: Separate parent controls from truncating text**

Wrap each parent category name in the macro with:

```html
<span class="category-name">
    <i class="category-disclosure" aria-hidden="true"></i>
    <i class="category-swatch" aria-hidden="true"></i>
    <span class="category-name__label">{{ category.category_name }}</span>
</span>
```

For standalone rows, keep the swatch and add the same
`.category-name__label` wrapper. Do not add a disclosure control to a leaf
row.

- [x] **Step 3: Align child bars and simplify guides**

Move child indentation to `.category-child__name` rather than the whole child
grid. Keep `.category-children` and `.category-child` unindented so every row
uses the same meter column. Replace `.category-child::before` with a short,
centered `.category-child__name::before` horizontal guide; retain muted child
labels and the smaller child meter.

- [x] **Step 4: Run the focused test to verify it passes**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: PASS.

### Task 3: Verify the cleanup

**Files:**

- Modify: `docs/superpowers/plans/2026-08-02-dashboard-category-row-polish.md`

**Interfaces:**

- Consumes: the final template, CSS, and dashboard regression tests.
- Produces: verification evidence for the polished report.

- [x] **Step 1: Run the dashboard test module**

Run: `task test -- tests/test_dashboard.py`

Expected: PASS.

- [x] **Step 2: Format and statically check the project**

Run: `task fix` then `task check`

Expected: both commands exit 0.

- [x] **Step 3: Run the full test suite**

Run: `task test`

Expected: report the existing package-version assertion mismatch if it remains
the only failure; do not change that unrelated test.
