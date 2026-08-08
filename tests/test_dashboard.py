"""Integration and service tests for the server-rendered dashboard."""

import datetime
import importlib
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, create_autospec

import pytest
from lunchmoney.models import BudgetSettingsResponseObject, SummaryResponseObject
from starlette.testclient import TestClient

from lunchmoney_mcp.app.dependencies import get_database, get_lunchmoney_app
from lunchmoney_mcp.app.main import fastapi_app
from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney_mcp.database.models import SyncMetadata
from lunchmoney_mcp.schemas import (
    AccountsSummary,
    GroupedSpendingResponse,
    ScheduledSyncStatus,
    SyncStatusSummary,
)
from lunchmoney_mcp.services.dashboard import DashboardData
from database.factories import (
    manual_account_object,
    plaid_account_object,
    transaction_object,
)


auth_module = importlib.import_module("lunchmoney_mcp.app.auth")
dashboard_router = importlib.import_module("lunchmoney_mcp.app.routers.dashboard")
dashboard_service = importlib.import_module("lunchmoney_mcp.services.dashboard")


def _budget_settings() -> BudgetSettingsResponseObject:
    """Create valid synthetic budget settings for dashboard rendering."""
    return BudgetSettingsResponseObject.model_validate(
        {
            "budget_period_granularity": "month",
            "budget_period_quantity": 1,
            "budget_period_anchor_date": "2026-01-01",
            "budget_hide_no_activity": False,
            "budget_use_last_day_of_month": False,
            "budget_income_option": "activity",
            "budget_rollover_left_to_budget": False,
        }
    )


def _dashboard_data(*, unavailable_sections: tuple[str, ...] = ()) -> DashboardData:
    """Create populated synthetic content for the dashboard template."""
    scheduled_sync = ScheduledSyncStatus(
        status="success",
        started_at=datetime.datetime(2026, 8, 2, 11, tzinfo=datetime.timezone.utc),
        finished_at=datetime.datetime(2026, 8, 2, 12, tzinfo=datetime.timezone.utc),
    )
    return DashboardData(
        period_start=datetime.date(2026, 8, 1),
        period_end=datetime.date(2026, 8, 2),
        previous_period_start=datetime.date(2026, 7, 1),
        next_period_start=None,
        transaction_last_synced_at=datetime.datetime(
            2026, 8, 2, 12, tzinfo=datetime.timezone.utc
        ),
        accounts=AccountsSummary(
            plaid_accounts=[
                plaid_account_object().model_copy(
                    update={
                        "id": 1,
                        "name": "Checking",
                        "display_name": None,
                        "type": "cash",
                        "balance": "1250.5000",
                        "currency": "usd",
                        "to_base": 1250.50,
                    }
                )
            ]
        ),
        budget_summary=SummaryResponseObject.model_validate(
            {"aligned": True, "categories": []}
        ),
        budget_settings=_budget_settings(),
        category_spending=GroupedSpendingResponse.model_validate(
            {
                "start_date": "2026-07-03",
                "end_date": "2026-08-02",
                "total_spending": 20,
                "total_income": 0,
                "categories": [
                    {
                        "category_id": 1,
                        "category_name": "Groceries",
                        "is_group": False,
                        "is_income": False,
                        "total_amount": 20,
                        "transaction_count": 1,
                        "children": [],
                    }
                ],
            }
        ),
        transactions=[
            transaction_object(transaction_id=1).model_copy(
                update={
                    "var_date": datetime.date(2026, 8, 2),
                    "payee": "<Synthetic payee>",
                    "amount": "20.0000",
                    "to_base": 20,
                }
            )
        ],
        scheduled_sync=scheduled_sync,
        sync_status=SyncStatusSummary(
            persistence_mode="Persistent (SQLite)",
            db_driver="sqlite+aiosqlite",
            db_url="sqlite+aiosqlite:///lunchmoney.db",
            stored_transactions=100,
            stored_categories=10,
            stored_accounts=2,
            stored_tags=1,
            transaction_cron="*/10 * * * *",
            transaction_timezone="UTC",
            transaction_last_synced_at=datetime.datetime(
                2026, 8, 2, 12, tzinfo=datetime.timezone.utc
            ),
            transaction_next_sync_at=datetime.datetime(
                2026, 8, 2, 12, 10, tzinfo=datetime.timezone.utc
            ),
            metadata_cron="0 * * * *",
            metadata_timezone="UTC",
            metadata_last_synced_at=datetime.datetime(
                2026, 8, 2, 12, tzinfo=datetime.timezone.utc
            ),
            metadata_next_sync_at=datetime.datetime(
                2026, 8, 2, 13, tzinfo=datetime.timezone.utc
            ),
            last_synced_at=datetime.datetime(
                2026, 8, 2, 12, tzinfo=datetime.timezone.utc
            ),
            schedule_cron="*/10 * * * *",
            schedule_timezone="UTC",
            next_sync_at=datetime.datetime(
                2026, 8, 2, 12, 10, tzinfo=datetime.timezone.utc
            ),
            embed_scheduler=False,
            scheduled_sync=scheduled_sync,
        ),
        unavailable_sections=unavailable_sections,
    )


def _configure_dashboard(
    monkeypatch: pytest.MonkeyPatch,
    data: DashboardData,
) -> None:
    """Patch the dashboard's dependencies with isolated rendering fixtures."""
    monkeypatch.setattr(
        dashboard_router,
        "fetch_dashboard_data",
        AsyncMock(return_value=data),
    )
    monkeypatch.setattr(
        auth_module,
        "get_secret_settings",
        lambda: SimpleNamespace(mcp_api_key="dashboard-key"),
    )
    fastapi_app.dependency_overrides[get_database] = lambda: object()
    fastapi_app.dependency_overrides[get_lunchmoney_app] = lambda: object()


def test_dashboard_requires_api_key_and_renders_populated_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Protect dashboard HTML and render accessible populated content when authorized."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            assert client.get("/").status_code == 401
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="dashboard-content"' in response.text
    assert "cockpit-layout" in response.text
    assert "Spending Breakdown" in response.text
    assert "dashboard.js" in response.text
    assert "Period summary" in response.text
    assert "Checking" in response.text
    assert "Groceries" in response.text
    assert "&lt;Synthetic payee&gt;" in response.text
    assert "vendor/htmx/htmx.min.js" in response.text
    assert "vendor/alpine/alpine.min.js" in response.text
    assert "vendor/pico/pico.min.css" in response.text
    with TestClient(fastapi_app, base_url="http://localhost") as client:
        stylesheet = client.get("/static/dashboard.css")
        script = client.get("/static/dashboard.js")
    assert stylesheet.status_code == 200
    assert "spending-workspace" in stylesheet.text
    assert script.status_code == 200
    assert "Alpine" in script.text


def test_dashboard_groups_accounts_and_uses_currency_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Group accounts by financial type and prefix balances with their currency."""
    data = _dashboard_data()
    data = replace(
        data,
        accounts=AccountsSummary(
            plaid_accounts=[
                plaid_account_object().model_copy(
                    update={
                        "id": 1,
                        "name": "Checking",
                        "display_name": "Daily spending",
                        "type": "cash",
                        "balance": "1250.5000",
                        "currency": "usd",
                        "to_base": 1250.50,
                    }
                ),
                plaid_account_object().model_copy(
                    update={
                        "id": 2,
                        "name": "Travel Card",
                        "display_name": "Travel card",
                        "type": "credit",
                        "balance": "210.2500",
                        "currency": "usd",
                        "to_base": 210.25,
                    }
                ),
                plaid_account_object().model_copy(
                    update={
                        "id": 5,
                        "name": "Savings",
                        "display_name": "Family savings",
                        "type": "cash",
                        "balance": "3000.0000",
                        "currency": "usd",
                        "to_base": 3000,
                    }
                ),
                plaid_account_object().model_copy(
                    update={
                        "id": 4,
                        "name": "Dormant Account",
                        "display_name": None,
                        "type": "cash",
                        "balance": "0.0000",
                        "currency": "usd",
                        "to_base": 0,
                    }
                ),
            ],
            manual_accounts=[
                manual_account_object().model_copy(
                    update={
                        "name": "Brokerage",
                        "display_name": None,
                        "type": "investment",
                        "balance": "5000.0000",
                        "currency": "usd",
                        "to_base": 5000,
                    }
                )
            ],
        ),
    )
    _configure_dashboard(monkeypatch=monkeypatch, data=data)
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Cash (2)" in response.text
    assert "Investment (1)" in response.text
    assert "Credit (1)" in response.text
    assert "$4,250.50" in response.text
    assert "$5,000.00" in response.text
    assert "$9,040.25" in response.text
    assert "Daily spending" in response.text
    assert "Family savings" in response.text
    assert "Checking" not in response.text
    assert response.text.index("Family savings") < response.text.index("Daily spending")
    assert "Connected" not in response.text
    assert "Manual" not in response.text
    assert "Dormant Account" not in response.text


def test_dashboard_renders_parent_categories_and_mascot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render grouped spending and the local brand mascot."""
    data = _dashboard_data()
    assert data.category_spending is not None
    data.category_spending.total_income = -100
    data.category_spending.total_spending = 30
    data.category_spending.categories = [
        {
            "category_id": 1,
            "category_name": "Food",
            "is_group": True,
            "is_income": False,
            "total_amount": 20,
            "transaction_count": 1,
            "children": [
                {
                    "category_id": 2,
                    "category_name": "Groceries",
                    "is_income": False,
                    "total_amount": 20,
                    "transaction_count": 1,
                },
                {
                    "category_id": 5,
                    "category_name": "No activity child",
                    "is_income": False,
                    "total_amount": 0,
                    "transaction_count": 0,
                },
            ],
        },
        {
            "category_id": 3,
            "category_name": "Salary",
            "is_group": False,
            "is_income": True,
            "total_amount": -100,
            "transaction_count": 1,
            "children": [],
        },
        {
            "category_id": 6,
            "category_name": "No activity category",
            "is_group": False,
            "is_income": False,
            "total_amount": 0,
            "transaction_count": 0,
            "children": [],
        },
        {
            "category_id": 4,
            "category_name": "Dining",
            "is_group": False,
            "is_income": False,
            "total_amount": 10,
            "transaction_count": 1,
            "children": [],
        },
    ]
    _configure_dashboard(monkeypatch=monkeypatch, data=data)
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
            css_response = client.get("/static/dashboard.css")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert css_response.status_code == 200
    assert 'class="category-item category-item--group' in response.text
    assert "<details" in response.text
    assert "category-disclosure" in response.text
    assert "category-child__meter" in response.text
    assert 'class="brand-mascot"' in response.text
    assert "/static/mascot.png" in response.text
    assert 'class="category-table"' in response.text
    assert 'class="category-table__columns"' in response.text
    assert 'class="category-section__heading">Income' in response.text
    assert 'class="category-section__heading">Expenses' in response.text
    assert "<em>100.0%</em>" in response.text
    assert "<em>-100.0%</em>" not in response.text
    assert 'class="category-name__label"' in response.text
    assert ".category-child__name::before" in css_response.text
    assert ".category-child__name::after" in css_response.text
    assert "data-category-filter" not in response.text
    assert response.text.index(">Salary</span") < response.text.index(">Food</span")
    assert response.text.index(">Food</span") < response.text.index(">Dining</span")
    assert "No activity category" not in response.text
    assert "No activity child" not in response.text


def test_dashboard_category_table_has_a_scrollable_region() -> None:
    """Keep a long category report scrollable within the dashboard panel."""
    with TestClient(fastapi_app, base_url="http://localhost") as client:
        response = client.get("/static/dashboard.css")

    assert response.status_code == 200
    assert ".category-table {\n    display: flex;" in response.text
    assert ".category-explorer {\n    flex: 1;" in response.text


def test_dashboard_renders_empty_and_unavailable_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render readable empty and partial-error states instead of JSON failures."""
    data = _dashboard_data(unavailable_sections=("Budget status",))
    data = replace(
        data,
        transaction_last_synced_at=None,
        accounts=AccountsSummary(),
        budget_summary=None,
        budget_settings=None,
        category_spending=GroupedSpendingResponse(
            start_date=data.period_start,
            end_date=data.period_end,
            total_spending=0,
            total_income=0,
            categories=[],
        ),
        transactions=[],
        scheduled_sync=None,
    )
    _configure_dashboard(monkeypatch=monkeypatch, data=data)
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Partial data" in response.text
    assert "No cached accounts yet" in response.text
    assert "Your ledger is quiet" in response.text


def test_dashboard_htmx_request_returns_content_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return only the content-area partial when HTMX sends HX-Request header."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/",
                headers={"X-API-Key": "dashboard-key", "HX-Request": "true"},
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert "spending-workspace" in response.text
    assert "Spending Breakdown" in response.text


def test_dashboard_htmx_targeted_request_returns_spending_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return only spending workspace partial when HTMX targets spending-workspace."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/",
                headers={
                    "X-API-Key": "dashboard-key",
                    "HX-Request": "true",
                    "HX-Target": "spending-workspace",
                },
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "spending-workspace" in response.text
    assert "Spending Breakdown" in response.text


def test_dashboard_htmx_request_excludes_full_page_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exclude <html>, <head>, and <body> tags from the HTMX partial response."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/",
                headers={"X-API-Key": "dashboard-key", "HX-Request": "true"},
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert "<html" not in response.text
    assert "<head" not in response.text
    assert "<body" not in response.text


def test_dashboard_passes_the_requested_period_to_its_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward a requested period date to the dashboard data loader."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/?period=2026-07-16", headers={"X-API-Key": "dashboard-key"}
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    dashboard_router.fetch_dashboard_data.assert_awaited_once_with(
        db=ANY,
        client=ANY,
        period_start=datetime.date(2026, 7, 16),
    )


def test_dashboard_htmx_request_includes_oob_period_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Include out-of-band period control in HTMX partial response."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/",
                headers={"X-API-Key": "dashboard-key", "HX-Request": "true"},
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'aria-label="Previous month"' in response.text


def test_dashboard_supports_month_format_period_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Support YYYY-MM month string format for period query parameter."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/?period=2026-05", headers={"X-API-Key": "dashboard-key"}
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    dashboard_router.fetch_dashboard_data.assert_awaited_once_with(
        db=ANY,
        client=ANY,
        period_start=datetime.date(2026, 5, 1),
    )


@pytest.mark.asyncio
async def test_dashboard_service_keeps_other_sections_available_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep cached content renderable when one live dashboard section fails."""
    database = create_autospec(LunchMoneyDatabase, instance=True)
    database.get_sync_metadata = AsyncMock(
        return_value=SyncMetadata(
            domain="transactions",
            last_synced_at=datetime.datetime(2026, 8, 2, tzinfo=datetime.timezone.utc),
        )
    )
    database.get_latest_scheduled_sync_run = AsyncMock(return_value=None)
    database.get_database_stats = AsyncMock(
        return_value={"transactions": 0, "categories": 0, "accounts": 0, "tags": 0}
    )
    accounts = AccountsSummary()
    spending = GroupedSpendingResponse(
        start_date=datetime.date(2026, 7, 3),
        end_date=datetime.date(2026, 8, 2),
        total_spending=0,
        total_income=0,
        categories=[],
    )
    monkeypatch.setattr(
        dashboard_service,
        "fetch_accounts",
        AsyncMock(return_value=accounts),
    )
    monkeypatch.setattr(
        dashboard_service,
        "fetch_account_summary",
        AsyncMock(side_effect=RuntimeError("upstream unavailable")),
    )
    monkeypatch.setattr(
        dashboard_service,
        "fetch_budget_settings",
        AsyncMock(return_value=_budget_settings()),
    )
    monkeypatch.setattr(
        dashboard_service,
        "fetch_category_spending",
        AsyncMock(return_value=spending),
    )
    monkeypatch.setattr(
        dashboard_service,
        "fetch_recent_transactions",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        dashboard_service,
        "get_scheduled_sync_status",
        AsyncMock(return_value=None),
    )

    data = await dashboard_service.fetch_dashboard_data(
        db=database,
        client=cast(LunchMoneyApp, object()),
        period_start=datetime.date(2026, 7, 16),
    )

    assert data.budget_summary is None
    assert data.accounts == accounts
    assert data.transaction_last_synced_at is not None
    assert data.unavailable_sections == ("Budget status",)
    assert data.period_start == datetime.date(2026, 7, 1)
    assert data.period_end == datetime.date(2026, 7, 31)
    dashboard_service.fetch_category_spending.assert_awaited_once_with(
        db=database,
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 31),
        days=None,
    )
    dashboard_service.fetch_recent_transactions.assert_awaited_once_with(
        db=database,
        limit=10,
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 31),
    )


def test_dashboard_renders_syncing_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render syncing status panel with persistence mode, schedules, and next sync estimate."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="sync-panel"' in response.text
    assert "Engine & Storage" in response.text
    assert "Database URL" in response.text
    assert "sqlite+aiosqlite:///lunchmoney.db" in response.text
    assert "Local DB Inventory" in response.text
    assert "Transactions Workload" in response.text
    assert "Metadata Workload" in response.text
    assert "Persistent (SQLite)" in response.text
    assert "*/10 * * * *" in response.text
    assert "0 * * * *" in response.text
    assert 'class="js-local-time"' in response.text


def test_humanize_time_ago() -> None:
    """Format timestamps into human-readable relative phrases."""
    from lunchmoney_mcp.services.dashboard import humanize_time_ago

    now = datetime.datetime.now(datetime.timezone.utc)
    assert humanize_time_ago(None) == "Not yet synced"
    assert (
        humanize_time_ago(now - datetime.timedelta(seconds=20), now=now) == "just now"
    )
    assert (
        humanize_time_ago(now - datetime.timedelta(minutes=5), now=now)
        == "5 minutes ago"
    )
    assert (
        humanize_time_ago(now - datetime.timedelta(hours=21), now=now) == "21 hours ago"
    )
    assert humanize_time_ago(now - datetime.timedelta(days=2), now=now) == "2 days ago"


def test_dashboard_renders_disabled_cron_workloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Render Disabled for cron schedule and next estimate when cron is unconfigured."""
    data = _dashboard_data()
    assert data.sync_status is not None
    disabled_status = data.sync_status.model_copy(
        update={
            "transaction_cron": None,
            "transaction_next_sync_at": None,
            "metadata_cron": None,
            "metadata_next_sync_at": None,
            "schedule_cron": None,
            "next_sync_at": None,
        }
    )
    disabled_data = replace(data, sync_status=disabled_status)
    _configure_dashboard(monkeypatch=monkeypatch, data=disabled_data)
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get("/", headers={"X-API-Key": "dashboard-key"})
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="sync-panel"' in response.text
    assert "Disabled" in response.text
    assert "Unknown" in response.text


def test_dashboard_sync_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trigger an instant sync via POST /dashboard/sync and re-render cockpit content."""
    from lunchmoney_mcp.services import sync as sync_service

    monkeypatch.setattr(
        sync_service,
        "execute_sync",
        AsyncMock(return_value=SimpleNamespace(synced=SimpleNamespace(user=1))),
    )
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.post(
                "/dashboard/sync",
                headers={"X-API-Key": "dashboard-key", "HX-Request": "true"},
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="sync-panel"' in response.text
    assert "Syncing status" in response.text


def test_dashboard_htmx_period_request_preserves_left_rail_when_targeting_dashboard_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve the left rail when an HTMX request with a period parameter targets dashboard-content."""
    _configure_dashboard(monkeypatch=monkeypatch, data=_dashboard_data())
    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            response = client.get(
                "/?period=2026-07-01",
                headers={
                    "X-API-Key": "dashboard-key",
                    "HX-Request": "true",
                    "HX-Target": "dashboard-content",
                },
            )
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'class="left-rail"' in response.text
