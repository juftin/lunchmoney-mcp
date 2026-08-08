# Dashboard category tree design

## Goal

Make the existing spending breakdown easier to scan by presenting each parent
category as an expandable group with its child categories nested beneath it in
the upstream dashboard's compact table style.

## Scope

- Keep the current monthly dashboard route and data service.
- Render Income first and Expenses second in one scrollable report; remove the
  income/expense filter.
- Keep a top-level category without children as a single row.
- Render each parent category as a native expandable row that is open initially;
  its total and share represent rolled-up spending; a chevron communicates its
  disclosure state.
- Render child categories beneath the parent with clear tree indentation,
  individual totals, and proportional meters.
- Sort each section's top-level categories by descending roll-up amount, and
  omit top-level and child categories with no spend.
- Replace the top-left "LM" brand mark with the supplied Lunch Money mascot as
  a decorative local asset.
- Restyle the spending workspace as a dense, upstream-inspired financial table:
  compact rows, stable category/meter/actual/share columns, category-colored
  bars, and strong parent/child indentation.
- Keep the existing actual and share data only; projected/budget columns are
  explicitly out of scope.

## Design

`fetch_category_spending()` already returns top-level categories with their
children and parent rollups. The dashboard template will use that existing
shape: a `details` element is the parent-group control and child rows are its
contents. It renders the Income section first, followed by Expenses, in one
scrollable table rather than separate panes. The summary remains the only
interactive element, so keyboard and screen-reader users get the native
expanded/collapsed semantics without a custom state store.

Child meters use the same income or expense total as the surrounding parent
row, so their length is comparable with every category shown in that view. The
parent's meter continues to show the roll-up total. CSS supplies compact table
spacing, aligned columns, a per-category color family, and the tree connector;
no new dashboard API or persistence is needed.

The supplied mascot is downloaded into the dashboard static assets and replaces
the top-left "LM" brand mark with empty alternative text. This preserves the
text brand as the link's accessible name and avoids a dependency on an external
request during dashboard rendering.

## Error handling

Existing unavailable and empty states remain unchanged. A parent category with
an empty child list renders as a normal standalone row.

## Verification

- Add rendering assertions for section order, roll-up sorting, zero-spend
  omission, a parent category, and its child row.
- Verify the dashboard test suite and project formatting, linting, type
  checking, and tests through the Taskfile.
