# 🤖 AGENTS.md — AI Agent Guidance & Coding Standards

Welcome, AI Coding Assistant! This document provides authoritative instructions, architectural guidelines, and workflow standards for working within the **`lunchmoney-mcp`** repository.

---

## 🗺️ Documentation Sitemap & Navigation Guide

When starting a task, use this directory map to locate specific documentation:

| Document                  | Path                                                 | Purpose                                                                    |
| :------------------------ | :--------------------------------------------------- | :------------------------------------------------------------------------- |
| **Active Checklist**      | [`docs/CHECKLIST.md`](docs/CHECKLIST.md)             | Task execution tracker. Check off items here when completed.               |
| **API Roadmap**           | [`docs/ROADMAP.md`](docs/ROADMAP.md)                 | 100% Lunch Money v2 API coverage matrix (39 endpoints) & sprint overview.  |
| **Incremental ETL Spec**  | [`docs/INCREMENTAL_ETL.md`](docs/INCREMENTAL_ETL.md) | Stateful sync, `SyncMetadata` watermark tracking & safety margin design.   |
| **Technical Handoff**     | [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md)     | Step-by-step code snippets, schema definitions, and sprint hand-off specs. |
| **MCP Integration Guide** | [`docs/MCP_GUIDE.md`](docs/MCP_GUIDE.md)             | stdio/SSE transports, `uvx` packaging, Resources, Prompts & OAuth.         |

---

## 🏛️ Project Overview & Architecture

**`lunchmoney-mcp`** is a high-performance Model Context Protocol (MCP) server and REST API for personal financial management with [Lunch Money](https://lunchmoney.app).

### System Topology

```
┌─────────────────────────────────────┐
│            Client Layer             │
│  (MCP Client / FastAPI REST Client) │
└──────────────────┬──────────────────┘
                   │
┌──────────────────┴──────────────────┐
│            Server Layer             │
│  FastAPI Routers  │  FastMCP Server │
└──────────────────┬──────────────────┘
                   │
┌──────────────────┴──────────────────┐
│            Service Layer            │
│  src/lunchmoney_mcp/services/       │
└──────────────────┬──────────────────┘
                   │
┌──────────────────┴──────────────────┐
│         Persistence Layer           │
│ SQLModel DB (SQLite/PG) │ Upstream  │
└─────────────────────────────────────┘
```

### 1-to-1 Parallel Domain Layering Matrix

For every Lunch Money domain (e.g. `categories`, `transactions`, `accounts`, `user`, `spending`, `sync`), there MUST be a matching 1-to-1 module file across all application layers:

| Domain Area             | DB Model (`database/models/`) | Service (`services/`) | FastAPI Router (`app/routers/`) | FastMCP Tool Module (`mcp/tools/`) |
| :---------------------- | :---------------------------- | :-------------------- | :------------------------------ | :--------------------------------- |
| **User & Profile**      | `user.py`                     | `user.py`             | `user.py`                       | `user.py`                          |
| **Categories**          | `categories.py`               | `categories.py`       | `categories.py`                 | `categories.py`                    |
| **Accounts**            | `accounts.py`                 | `accounts.py`         | `accounts.py`                   | `accounts.py`                      |
| **Transactions**        | `transactions.py`             | `transactions.py`     | `transactions.py`               | `transactions.py`                  |
| **Spending Analytics**  | `transactions.py`             | `spending.py`         | `spending.py`                   | `spending.py`                      |
| **Sync & Watermarks**   | `sync.py`                     | `sync.py`             | `sync.py`                       | `sync.py`                          |
| **Tags (Planned)**      | `tags.py`                     | `tags.py`             | `tags.py`                       | `tags.py`                          |
| **Recurring (Planned)** | `recurring.py`                | `recurring.py`        | `recurring.py`                  | `recurring.py`                     |
| **Budgets (Planned)**   | `budgets.py`                  | `budgets.py`          | `budgets.py`                    | `budgets.py`                       |

### Architectural Principles

1. **Service Layer Isolation**:
    - All business logic, DB queries, API calls, and domain rollups MUST reside in `src/lunchmoney_mcp/services/`.
    - FastAPI routers (`src/lunchmoney_mcp/app/routers/`) and FastMCP tools (`src/lunchmoney_mcp/mcp/tools/`) MUST be clean 1-to-2 line delegators calling service functions.

2. **Modular MCP Tool Organization**:
    - FastMCP tools MUST be defined in dedicated domain files under `src/lunchmoney_mcp/mcp/tools/` and imported into `src/lunchmoney_mcp/mcp/server.py`.
    - FastMCP tools and FastAPI routers delegate directly to clean service functions in `src/lunchmoney_mcp/services/`.

3. **Upstream-First Write-Back Strategy**:
    - All write operations (create/update/delete) MUST call the Lunch Money v2 API first.
    - Upon receiving the canonical API response object, convert it to a SQLModel record (`Model.from_api()`) and execute `await db.upsert()` or `await db.delete()`.

4. **Dual Persistence Modes**:
    - **Persistent Mode (Default)**: Uses SQLite file (`lunchmoney.db`) or PostgreSQL URL (`LUNCHMONEY_DATABASE_URL`).
    - **Stateless Mode (`STATELESS=true`)**: Uses shared in-memory SQLite (`sqlite+aiosqlite:///file:memdb?mode=memory&cache=shared&uri=true`) with `StaticPool` and live API refresh per operation.

5. **Opt-In Incremental ETL**:
    - Default sync (`incremental=False`) uses rolling date window (`days=30`).
    - Incremental sync (`incremental=True`) queries `SyncMetadata` for domain watermarks with a safety overlap buffer (`LUNCHMONEY_SYNC_SAFETY_MARGIN_MINUTES`, default 5 mins).

6. **Distributed Locking & Zero-Infrastructure Fallback**:
    - Migration and synchronization operations MUST acquire a distributed lock (`get_migration_lock()`) to guarantee single-worker execution across multi-container environments.
    - When `REDIS_URL` is set, `RedisLock` is used for distributed coordination across instances.
    - When `REDIS_URL` is omitted, the app gracefully falls back to local file-based `LockFile` (`.lunchmoney_*.lock`), requiring zero external infrastructure setup for desktop/CLI usage.

---

## ⚡ Subagent Creation & Task Parallelization Protocol

When executing tasks that contain independent sub-components (e.g. implementing multiple read-only service functions, writing unit test files, or creating documentation pages):

1. **Define Specialized Subagents (`define_subagent`)**:
    - Create focused subagent types (e.g., `EndpointBuilder`, `TestWriter`, `DocUpdater`) with minimal required tool permissions.
2. **Invoke Subagents Concurrently (`invoke_subagent`)**:
    - Launch subagents with clear, explicit target file paths and acceptance criteria.
3. **Reactive Execution (No Polling)**:
    - Do NOT poll or check status in a loop. Stop tool execution or proceed with other work; the environment will automatically notify you when subagents finish.

---

## 📝 Documentation Auto-Improvement & Checklist Updates

1. **Checkoff Protocol**: When completing a task, immediately edit [`docs/CHECKLIST.md`](docs/CHECKLIST.md) to check off the item (`- [x]`).
2. **Auto-Improvement Rule**: Whenever you modify code signatures, add configuration options, or resolve subtle bugs, update the relevant specification in `docs/` (`ROADMAP.md`, `INCREMENTAL_ETL.md`, `AGENT_HANDOFF.md`, or `MCP_GUIDE.md`).
3. **New Tasks**: If a task reveals additional requirements, add new `- [ ]` checklist items to `docs/CHECKLIST.md`.

---

## 🛠️ Development Workflows & Tooling

Most workflows are orchestrated via [`go-task`](https://taskfile.dev). ALWAYS use `task` commands rather than invoking underlying tools directly.

### Standard Entrypoints

| Command         | Action                                                                              |
| :-------------- | :---------------------------------------------------------------------------------- |
| `task install`  | Install project and development dependencies (`uv sync`)                            |
| `task fix`      | Auto-fix code formatting and lint issues (`ruff format` & `ruff check --fix`)       |
| `task lint`     | Check formatting and linting rules (`ruff`)                                         |
| `task check`    | Perform static type checking (`ty check`)                                           |
| `task test`     | Execute Pytest test suite (`pytest`)                                                |
| `task dev`      | Run local FastAPI dev server (`uv run fastapi dev src/lunchmoney_mcp/app/main.py`)  |
| `task notebook` | Launch interactive marimo usage notebook (`marimo edit notebooks/example_usage.py`) |

---

## 📋 Code Quality & Style Guidelines

### Python Style & Docstrings

- **Type Hints**: Annotate every function and method parameters and return types (`def test_foo() -> None:`). Use modern Python 3.10+ union types (`int | None`).
- **Docstrings**: NumPy style docstrings (`Parameters`, `Returns`, `Raises`, `Notes`) on all modules, classes, and functions. Use `AttributeDocStrings` for class fields.
- **Imports**: Group imports cleanly. Avoid unused imports.

### Verification Protocol

Before committing code, ALWAYS run:

```bash
task fix && task lint && task check && task test
```

All four tasks must exit with code `0`.

### Git Commitment Protocol

Use Gitmoji commit conventions:

```
<intention> [scope?][:?] <message>
```

**Common Intention Emojis**:

- ✨ (`:sparkles:`): New feature
- 🐛 (`:bug:`): Bug fix
- ⚡️ (`:zap:`): Performance improvement
- ♻️ (`:recycle:`): Refactoring
- 🧪 (`:test_tube:`): Adding tests
- 📝 (`:memo:`): Documentation update
- 🔧 (`:wrench:`): Configuration change
