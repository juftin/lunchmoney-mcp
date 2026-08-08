# Dashboard Category Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render spending parents as accessible expandable groups with visual child hierarchy, and replace the top-left brand mark with the supplied mascot.

**Architecture:** The existing `GroupedSpendingResponse` supplies parent roll-ups and children, so this changes only the server-rendered template, dashboard styles, static asset, and rendering test. Native `details`/`summary` starts open and retains accessible disclosure behavior; the template renders an Income section followed by an Expenses section, with each top-level list sorted by its roll-up amount.

**Tech Stack:** Jinja2, CSS, browser-native disclosure controls, pytest, Taskfile, downloaded PNG static asset.

## Global Constraints

- Reuse `fetch_category_spending()`; do not add API, service, or database state.
- Render Income and Expenses together, omit zero-spend categories, and preserve empty and unavailable states.
- Download the supplied mascot locally, use it as the top-left brand mark, and render it with empty alternative text.
- Use Taskfile entrypoints for verification.

---

### Task 1: Test hierarchy and mascot rendering

**Files:**

- Modify/Test: `tests/test_dashboard.py`

**Interfaces:**

- Consumes: `_dashboard_data()` and the authenticated `GET /` dashboard endpoint.
- Produces: a regression test requiring a parent `details` group, child meter, and local `brand-mascot` reference.

- [x] **Step 1: Write the failing test**

```python
def test_dashboard_renders_parent_categories_and_mascot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render grouped spending and the local brand mascot."""
    # Configure a parent "Food" category with a "Groceries" child,
    # request the authorized dashboard, then assert its hierarchy and mascot.
```

- [x] **Step 2: Run test to verify it fails**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: FAIL because the fixture and dashboard do not yet expose the asserted category-tree and mascot markup.

### Task 2: Render the local mascot and category tree

**Files:**

- Create: `src/lunchmoney_mcp/app/static/mascot.png`
- Modify: `src/lunchmoney_mcp/app/templates/dashboard.html`
- Modify: `src/lunchmoney_mcp/app/static/dashboard.css`
- Test: `tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

**Interfaces:**

- Consumes: `CategorySpending.children`, `ChildCategorySpending.total_amount`, and the `/static` route.
- Produces: child rows with `category-child__meter` and a mascot image referenced through `url_for('dashboard_static', path='/mascot.png')`.

- [x] **Step 1: Download the supplied mascot asset**

Run: `curl --fail --location --output src/lunchmoney_mcp/app/static/mascot.png https://lunchmoney.app/assets/images/logos/mascot.png`

- [x] **Step 2: Render the mascot and nested child rows**

Use a decorative image in place of the top-left `LM` brand mark:

```html
<img
    class="brand-mascot"
    src="{{ url_for('dashboard_static', path='/mascot.png') }}"
    alt=""
/>
```

For each child, calculate its percentage against the same income or expense total as its parent; render the child name, meter, amount, and percentage. Render Income before Expenses, sort each section by descending top-level roll-up amount, and omit zero-spend parent and child rows.

- [x] **Step 3: Add scoped hierarchy styling**

Style `.brand-mascot`, `.category-section__heading`, `.category-item--group`, `.category-children`, `.category-child`, and `.category-child__meter` to create a compact nested tree and reuse the parent swatch color for child meters.

- [x] **Step 4: Run the regression test to verify it passes**

Run: `task test -- tests/test_dashboard.py::test_dashboard_renders_parent_categories_and_mascot`

Expected: PASS.

### Task 3: Verify and record the dashboard change

**Files:**

- Modify: `docs/CHECKLIST.md`

**Interfaces:**

- Consumes: passing project checks.
- Produces: completed dashboard interaction entry under Sprint 11.

- [ ] **Step 1: Run focused dashboard tests**

Run: `task test -- tests/test_dashboard.py`

Expected: PASS.

- [ ] **Step 2: Apply quality fixes and run all checks**

Run: `task fix && task lint && task check && task test`

Expected: every command exits 0.

- [ ] **Step 3: Record completion and commit**

Add this completed Sprint 11 entry:

```markdown
- [x] **Interactive Category Tree**: Group dashboard spending by parent category with accessible child disclosure and a local mascot welcome illustration.
```

Commit the implementation with `✨ (dashboard): group spending by parent category`.
