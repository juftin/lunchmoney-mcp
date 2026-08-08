# 📋 Master Development Checklist & Agent Execution Guide

This document serves as the **operational task tracker** for **`lunchmoney-mcp`**. Every task across all implementation sprints is tracked here. AI agents and developers working on this project MUST follow the execution rules below.

---

## 🤖 Agent Operating Rules & Parallelization

### 1. How to Claim and Update Checklist Items

- Before starting a task, read the referenced specification in [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md) or [`docs/ROADMAP.md`](ROADMAP.md).
- When a task is fully verified (`task fix && task lint && task check && task test`), update this document by changing `- [ ]` to `- [x]`.
- If your work discovers new requirements, edge cases, or sub-tasks, immediately add new checklist items under the appropriate sprint section.

### 2. Subagent Creation & Parallelization Protocol

When a sprint contains independent, non-overlapping tasks (e.g. creating parallel service functions, adding independent endpoints, or writing unit tests), invoke subagents to execute them concurrently:

1. **Define Subagents (`define_subagent`)**:
    - Define specialized subagent roles (e.g., `EndpointBuilder`, `TestWriter`, `ServiceImplementor`).
2. **Invoke Subagents (`invoke_subagent`)**:
    - Launch subagents with clear, self-contained prompts specifying the target files and verification expectations.
3. **Reactive Notification (No Polling)**:
    - After launching subagents, do NOT poll in a loop. Stop tool calls or proceed with independent work until the system automatically notifies you upon completion.

---

## 🎯 Master Implementation Checklist

### 🏁 Sprint 0: Incremental ETL & Stateless Engine

_Reference Spec_: [`docs/INCREMENTAL_ETL.md`](INCREMENTAL_ETL.md) & [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-0-incremental-etl--stateless-engine)

- [x] **MCP Tools Modularization**: Refactor FastMCP tools into modular domain package in [`src/lunchmoney_mcp/mcp/tools/`](../src/lunchmoney_mcp/mcp/tools/).
- [x] **Config Additions**: Add `stateless: bool` (`LUNCHMONEY_STATELESS`) and `sync_safety_margin_minutes: int` (`LUNCHMONEY_SYNC_SAFETY_MARGIN_MINUTES`) in [`src/lunchmoney_mcp/config.py`](../src/lunchmoney_mcp/config.py).
- [x] **SyncMetadata Model**: Create `SyncMetadata` table in [`src/lunchmoney_mcp/database/models/sync.py`](../src/lunchmoney_mcp/database/models/sync.py).
- [x] **Alembic Migration**: Add migration `0002_add_sync_metadata_table.py` for `sync_metadata`.
- [x] **Stateless In-Memory Database**: Update [`src/lunchmoney_mcp/database/backend.py`](../src/lunchmoney_mcp/database/backend.py) to support `StaticPool` in-memory SQLite and `create_tables()` helper.
- [x] **Opt-In Incremental Sync Logic**: Update [`src/lunchmoney_mcp/app/sync.py`](../src/lunchmoney_mcp/app/sync.py) & [`src/lunchmoney_mcp/services/sync.py`](../src/lunchmoney_mcp/services/sync.py) to handle transaction-only `incremental: bool = False` and `updated_since` timestamp filtering.
- [x] **Router & Tool Integration**: Expose `incremental` and `safety_margin_minutes` parameters on `POST /api/sync` and `sync_data` FastMCP tool.
- [x] **Test Suite**: Cover stateless configuration, database initialization, migrations, incremental transaction policy, and transport delegation in `tests/test_config.py`, `tests/database/test_backend.py`, `tests/database/test_migrations.py`, `tests/test_incremental_sync.py`, `tests/test_app.py`, and `tests/test_mcp.py`.

---

### 📖 Sprint 1: Read-Only 100% v2 API Coverage

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#1-user--account-summary-me-summary) & [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-1-complete-read-only-100-v2-api-coverage)

- [x] **Account Summary**: Implement `fetch_account_summary`, `GET /api/summary`, and `get_account_summary` FastMCP tool.
- [x] **Tags Queries**: Implement `fetch_tags`, `fetch_tag_by_id`, `GET /api/tags`, `GET /api/tags/{id}`, `list_tags`, and `get_tag` tools.
- [x] **Recurring Items Queries**: Implement `fetch_recurring_items`, `fetch_recurring_item_by_id`, `GET /api/recurring_items`, `GET /api/recurring_items/{id}`, `list_recurring_items`, and `get_recurring_item` tools.
- [x] **Single-ID Category Lookup**: Implement `GET /api/categories/{id}` and `get_category` FastMCP tool.
- [x] **Single-ID Account Lookups**: Implement `GET /api/manual_accounts/{id}` (`get_manual_account`) and `GET /api/plaid_accounts/{id}` (`get_plaid_account`).
- [x] **Single-ID Transaction Lookup**: Implement `GET /api/transactions/{id}` and `get_transaction` FastMCP tool.
- [x] **Test Suite**: Add tests for all read-only endpoints in `tests/test_read_only.py`.

---

### ✍️ Sprint 2: Category & Manual Account Mutations

_Reference Spec_: [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-2-category--manual-account-mutations)

- [x] **Category Creation**: Implement Upstream-First `create_category` service, `POST /api/categories`, and FastMCP tool.
- [x] **Category Update**: Implement Upstream-First `update_category` service, `PUT /api/categories/{id}`, and FastMCP tool.
- [x] **Category Deletion**: Implement Upstream-First `delete_category` service, `DELETE /api/categories/{id}`, and FastMCP tool.
- [x] **Manual Account Creation**: Implement Upstream-First `create_manual_account` service, `POST /api/manual_accounts`, and FastMCP tool.
- [x] **Manual Account Update**: Implement Upstream-First `update_manual_account` service, `PUT /api/manual_accounts/{id}`, and FastMCP tool.
- [x] **Manual Account Deletion**: Implement Upstream-First `delete_manual_account` service, `DELETE /api/manual_accounts/{id}`, and FastMCP tool.
- [x] **Plaid Fetch Trigger**: Implement `trigger_plaid_fetch` service, `POST /api/plaid_accounts/fetch`, and FastMCP tool.
- [x] **Test Suite**: Add unit and integration tests in `tests/test_category_account_mutations.py`.

---

### 💳 Sprint 3: Transaction Mutations, Grouping, Splitting & Attachments

_Reference Spec_: [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-3-transaction-mutations-grouping-splitting--attachments)

- [x] **Single Transaction Insert**: Implement `create_transactions` (`POST /api/transactions`).
- [x] **Bulk Transaction Update**: Implement `bulk_update_transactions` (`PUT /api/transactions`).
- [x] **Bulk Transaction Delete**: Implement `bulk_delete_transactions` (`DELETE /api/transactions`).
- [x] **Single Transaction Update**: Implement `update_transaction` (`PUT /api/transactions/{id}`).
- [x] **Single Transaction Delete**: Implement `delete_transaction` (`DELETE /api/transactions/{id}`).
- [x] **Transaction Grouping**: Implement `group_transactions` (`POST /api/transactions/group`) and `ungroup_transactions` (`DELETE /api/transactions/group/{id}`).
- [x] **Transaction Splitting**: Implement `split_transaction` (`POST /api/transactions/split/{id}`) and `unsplit_transaction` (`DELETE /api/transactions/split/{id}`).
- [x] **Transaction Attachments**: Implement attachment upload (`POST /api/transactions/{id}/attachments`), download (`GET /api/transactions/attachments/{file_id}`), and delete (`DELETE /api/transactions/attachments/{file_id}`).
- [x] **Test Suite**: Add comprehensive test suite in `tests/test_transaction_mutations.py`.

---

### 📊 Sprint 4: Budgets & Time-Series Spending Trends

_Reference Spec_: [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-4-budgets--spending-trends)

- [x] **Budget Settings**: Implement `fetch_budget_settings`, `GET /api/budgets/settings`, and `get_budget_settings` tool.
- [x] **Budget Upsert**: Implement `set_budget_value`, `PUT /api/budgets`, and `upsert_budget` tool.
- [x] **Budget Clear**: Implement `clear_budget_value`, `DELETE /api/budgets`, and `clear_budget` tool.
- [x] **Spending Trends Analysis**: Implement `fetch_spending_trends` (daily/weekly/monthly time-series aggregation), `GET /api/spending/trends`, and `get_spending_trends` tool.
- [x] **Test Suite**: Add test suite in `tests/test_budgets_trends.py`.

---

### 🛡️ Sprint 5: Production Security, MCP Primitives & CI/CD

_Reference Spec_: [`docs/MCP_GUIDE.md`](MCP_GUIDE.md) & [`docs/AGENT_HANDOFF.md`](AGENT_HANDOFF.md#sprint-5-production-security--cicd)

- [x] **API Key Guard**: Implement `verify_api_key` middleware in [`src/lunchmoney_mcp/app/auth.py`](../src/lunchmoney_mcp/app/auth.py).
- [x] **MCP Executable Entrypoint**: Add `lunchmoney-mcp = "lunchmoney_mcp.mcp.server:main"` script in `pyproject.toml`.
- [x] **MCP Multi-Transport**: Support `--sse` transport flag in `mcp.run()`.
- [x] **MCP Resources**: Register `lunchmoney://summary` and `lunchmoney://categories` resources in [`src/lunchmoney_mcp/mcp/server.py`](../src/lunchmoney_mcp/mcp/server.py).
- [x] **MCP Prompts**: Register `budget_health_check` and `uncategorized_transactions_audit` prompts.
- [x] **GitHub Actions CI**: Add `.github/workflows/ci.yaml` running `task lint`, `task check`, `task test`, and `docker build`.

---

### 🔐 Sprint 6: Remote MCP OAuth & Roadmap Reconciliation

- [x] **OIDC OAuth Proxy**: Add optional OAuth 2.1 protection for remote MCP HTTP transports using an OIDC discovery URL.
- [x] **OAuth Configuration**: Document the public base URL, identity-provider settings, and local unauthenticated default.
- [x] **Roadmap Reconciliation**: Mark delivered transaction operations and Sprint 4 production work as complete in `docs/ROADMAP.md`.

---

### 🏷️ Sprint 7: Tag Mutations & API Coverage Completion

- [x] **Tag Creation**: Implement Upstream-First `create_tag`, `POST /api/tags`, and FastMCP tool.
- [x] **Tag Update**: Implement Upstream-First `update_tag`, `PUT /api/tags/{id}`, and FastMCP tool.
- [x] **Tag Deletion**: Implement Upstream-First `delete_tag`, `DELETE /api/tags/{id}`, and FastMCP tool with cached transaction-link reconciliation.
- [x] **Test Suite**: Add regression coverage for tag mutation delegation, cache updates, routes, and MCP tools.

---

### ⏱️ Sprint 8: Production Runtime & Scheduled Sync

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#sprint-8-production-runtime--scheduled-sync)

- [x] **Gunicorn Runtime**: Replace FastAPI CLI deployment commands with Gunicorn and the maintained Uvicorn worker package; retain direct Uvicorn for local development.
- [x] **Dedicated Scheduler**: Add an opt-in `lunchmoney-mcp schedule` APScheduler process with configurable cron, timezone, graceful lifecycle, and sync run reporting; each run refreshes full metadata and incrementally refreshes transactions.
- [x] **Multi-Worker Safety**: Ensure Gunicorn workers never start schedulers; serialize scheduled syncs with the distributed lock and test duplicate-prevention behavior.
- [x] **Stable Scheduler Constraint**: Use one dedicated APScheduler 3.11 process; HA/multi-scheduler operation is explicitly unsupported because APScheduler 3 job stores cannot be shared.
- [x] **Local Embedded Scheduler**: Allow an explicitly configured, single-worker development FastAPI process to run the scheduler through its lifespan; reject Gunicorn and multi-worker modes.

### 🔎 Sprint 9: Upstream API Compatibility & Coverage Audit

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#sprint-9-upstream-api-compatibility--coverage-audit)

- [x] **Spec Drift Detection**: Pin/regenerate the generated client and fail CI when endpoint, schema, or enum changes are not reconciled.
- [x] **Coverage Manifest**: Verify every supported upstream operation has a service, REST, and MCP mapping.
- [x] **Upstream Contract Tests**: Exercise the mock service or a disposable test budget without real financial data.
- [x] **Response Fidelity**: Return complete generated Lunch Money resource models from cached REST and MCP endpoints; retain derived summaries only for analytics and sync operations.
- [x] **Transaction Query Fidelity**: Make `GET /api/transactions` select the configured live or persisted source, apply Lunch Money filters, consume upstream pagination internally, and return every match in one flat collection.
- [x] **Category Query Fidelity**: Make `GET /api/categories` select the configured live or persisted source, accept Lunch Money's hierarchy and group controls, and return a flat collection.
- [x] **Collection Response Simplicity**: Return flat collections for direct collection endpoints; reserve the combined `/accounts` envelope for its two account sources.

### 🛡️ Sprint 10: Operational Hardening & Observability

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#sprint-10-operational-hardening--observability)

- [x] **Health and Telemetry**: Add health/readiness checks, safe structured logs, request IDs, and Prometheus-compatible `/metrics` operational metrics protected by network policy or authentication.
- [x] **Network Hardening**: Apply secure proxy, host, CORS, size, timeout, concurrency, and rate-limit defaults.
- [x] **Deployment Safety**: Add security scanning, container hardening, backup/restore guidance, and production smoke tests.

### 📈 Sprint 11: Server-Rendered Financial Dashboard

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#sprint-11-server-rendered-financial-dashboard)

- [x] **HTML Dashboard**: Add authenticated, accessible single-user, single-account server-rendered summary, spending, budget, transaction, and sync-status views without a separate JavaScript application.
- [x] **Service Reuse**: Keep dashboard routes as thin delegators to existing services and test authorized, empty, and error rendering.
- [ ] **Interactive Category Tree**: Group dashboard spending by parent category with accessible child disclosure and a local mascot brand mark.

### 🧰 Sprint 12: CLI, Packaging & Operator Experience

_Reference Spec_: [`docs/ROADMAP.md`](ROADMAP.md#sprint-12-cli-packaging--operator-experience)

- [x] **CLI Subcommands**: Provide `mcp`, `serve`, `schedule`, `sync`, `doctor`, and `version` with safe configuration validation and meaningful exit codes.
- [x] **Deployment Docs**: Make Docker Compose the first-class deployment path and document package, scheduler, and upgrade workflows.

---

## 📝 Documentation Auto-Improvement Protocol

Whenever an agent completes a task, refactor code, or modify a signature:

1. Update docstrings on touched functions, classes, and modules (NumPy format).
2. Check off completed items in this document (`docs/CHECKLIST.md`).
3. If new APIs, parameters, or edge cases are added, update the relevant specification in `docs/ROADMAP.md` or `docs/AGENT_HANDOFF.md`.
