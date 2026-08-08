# Dashboard category-row polish design

## Goal

Polish the current spending dashboard without changing its layout, route, or
transaction-classification rules. The category table should have complete
disclosure affordances, calmer child rows, and non-negative income shares.

## Scope

- Keep the existing one-panel dashboard and scrollable category report.
- Prevent the parent-row disclosure chevron from being clipped by the category
  label's truncation container.
- Replace the heavy child-row tree treatment with a small, consistent indent
  and a subtle leading rule. Child meters remain aligned with parent meters so
  values are comparable down the table.
- Preserve top-level colored swatches, row sorting, zero-spend omission, and
  native `details` disclosure behavior.
- Calculate display shares with an absolute section denominator so income
  shares are not shown as negative values.

## Non-goals

- Do not rebuild the dashboard as a single-page application.
- Do not change how the spending service classifies transactions or calculates
  aggregate income and expense totals.
- Do not add a budget or projected-spend column.

## Design

The disclosure icon lives outside the truncating text span, leaving enough
space for its rotated geometry and making the open/closed control readable.
Children use a modest left inset and a short horizontal guide instead of a
full-height tree connector. Their labels and meters remain subdued, while the
amount and share columns continue to align with their parent row.

The template computes a share from `abs(category amount) / abs(section total)`
to remove sign artifacts from income. A share can still exceed 100% when the
underlying section total is a net of offsetting transactions; correcting that
requires an explicit product decision about transfers and investment activity,
so it remains out of scope.

## Verification

- Add rendering coverage for an absolute income share and the child-row hooks.
- Verify the focused dashboard test suite, formatter, lint/type check, and the
  full suite through the Taskfile. Report the pre-existing package-version test
  mismatch if it remains the only full-suite failure.
