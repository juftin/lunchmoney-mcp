"""Regression tests for Sprint 4 budget and spending-trend features."""

import datetime
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock

import pytest
import pytest_asyncio
from lunchmoney.models import (
    BudgetSettingsResponseObject,
    BudgetUpsertResponseObject,
    UpsertBudgetRequestObject,
    UpsertBudgetRequestObjectAmount,
)

from lunchmoney_mcp.app.main import fastapi_app
from lunchmoney_mcp.client import LunchableData, LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase, run_migrations
from lunchmoney_mcp.database.models import Category, Transaction
from lunchmoney_mcp.mcp import mcp
from lunchmoney_mcp.services import (
    clear_budget_value,
    fetch_budget_settings,
    fetch_spending_trends,
    set_budget_value,
)
from database.factories import category_object, transaction_object


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[LunchMoneyDatabase]:
    """Provide an initialized SQLite database for time-series tests."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'budgets-trends.db'}"
    await run_migrations(db_url)
    async with LunchMoneyDatabase(db_url) as db:
        yield db


def _budget_settings() -> BudgetSettingsResponseObject:
    """Create a valid budget-settings response for live-query tests."""
    return BudgetSettingsResponseObject.model_validate(
        {
            "budget_period_granularity": "month",
            "budget_period_quantity": 1,
            "budget_period_anchor_date": "2026-01-01",
            "budget_hide_no_activity": False,
            "budget_use_last_day_of_month": True,
            "budget_income_option": "activity",
            "budget_rollover_left_to_budget": False,
        }
    )


def _budget_request() -> UpsertBudgetRequestObject:
    """Create a valid budget-value request for mutation tests."""
    return UpsertBudgetRequestObject(
        category_id=17,
        start_date=datetime.date(2026, 1, 1),
        amount=UpsertBudgetRequestObjectAmount.model_construct(actual_instance="120"),
        notes="Synthetic budget",
    )


def _budget_response() -> BudgetUpsertResponseObject:
    """Create a canonical upstream budget-value response for tests."""
    return BudgetUpsertResponseObject.model_validate(
        {
            "category_id": 17,
            "start_date": "2026-01-01",
            "amount": "120",
            "currency": "usd",
            "to_base": 120,
            "notes": "Synthetic budget",
        }
    )


@pytest.mark.asyncio
async def test_budget_settings_service_forwards_to_lunch_money_client() -> None:
    """Fetch budget settings from the generated Lunch Money API client."""
    settings = _budget_settings()
    get_budget_settings = AsyncMock(return_value=settings)
    client = cast(
        LunchMoneyApp,
        SimpleNamespace(
            data=LunchableData(),
            client=SimpleNamespace(
                budgets=SimpleNamespace(get_budget_settings=get_budget_settings)
            ),
        ),
    )

    result = await fetch_budget_settings(client=client, force_refresh=True)

    assert result == settings
    get_budget_settings.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_budget_mutation_services_forward_to_lunch_money_client() -> None:
    """Set and clear budget values through the generated API client."""
    request = _budget_request()
    response = _budget_response()
    upsert_budget = AsyncMock(return_value=response)
    delete_budget = AsyncMock()
    client = cast(
        LunchMoneyApp,
        SimpleNamespace(
            data=LunchableData(),
            client=SimpleNamespace(
                budgets=SimpleNamespace(
                    upsert_budget=upsert_budget,
                    delete_budget=delete_budget,
                )
            ),
        ),
    )

    result = await set_budget_value(client=client, request=request)
    await clear_budget_value(
        client=client,
        category_id=request.category_id,
        start_date=request.start_date,
    )

    assert result == response
    upsert_budget.assert_awaited_once_with(upsert_budget_request_object=request)
    delete_budget.assert_awaited_once_with(
        category_id=request.category_id,
        start_date=request.start_date,
    )


@pytest.mark.asyncio
async def test_spending_trends_aggregate_calendar_periods(
    database: LunchMoneyDatabase,
) -> None:
    """Bucket synchronized income and expense transactions by calendar period."""
    expense_category = Category.from_api(
        category_object(children=[]).model_copy(update={"id": 10, "is_income": False})
    )
    income_category = Category.from_api(
        category_object(children=[]).model_copy(update={"id": 20, "is_income": True})
    )
    await database.upsert(expense_category)
    await database.upsert(income_category)

    for transaction_id, var_date, amount, category_id in [
        (101, datetime.date(2026, 1, 5), Decimal("10"), 10),
        (102, datetime.date(2026, 1, 7), Decimal("100"), 20),
        (103, datetime.date(2026, 1, 12), Decimal("20"), 10),
    ]:
        transaction = Transaction.from_api(
            transaction_object().model_copy(
                update={
                    "id": transaction_id,
                    "date": var_date,
                    "var_date": var_date,
                    "amount": amount,
                    "category_id": category_id,
                    "plaid_account_id": None,
                    "manual_account_id": None,
                    "tags": [],
                    "tag_ids": [],
                    "is_split_parent": False,
                    "split_parent_id": None,
                }
            )
        )
        await database.upsert(transaction)

    response = await fetch_spending_trends(
        db=database,
        granularity="weekly",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 31),
    )

    assert response.granularity == "weekly"
    assert [
        (trend.start_date, trend.total_spending, trend.total_income)
        for trend in response.trends
    ] == [
        (datetime.date(2026, 1, 5), 10.0, 100.0),
        (datetime.date(2026, 1, 12), 20.0, 0.0),
    ]

    daily = await fetch_spending_trends(
        db=database,
        granularity="daily",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 31),
    )
    monthly = await fetch_spending_trends(
        db=database,
        granularity="monthly",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 31),
    )

    assert [trend.start_date for trend in daily.trends] == [
        datetime.date(2026, 1, 5),
        datetime.date(2026, 1, 7),
        datetime.date(2026, 1, 12),
    ]
    assert monthly.trends[0].start_date == datetime.date(2026, 1, 1)
    assert monthly.trends[0].total_spending == 30.0
    assert monthly.trends[0].total_income == 100.0


def test_budget_settings_route_is_registered() -> None:
    """Publish the budget-settings endpoint in the OpenAPI document."""
    operation = fastapi_app.openapi()["paths"]["/api/budgets/settings"]["get"]

    assert operation["operationId"] == "get_budget_settings"
    paths = fastapi_app.openapi()["paths"]
    assert paths["/api/budgets"]["put"]["operationId"] == "upsert_budget"
    assert paths["/api/budgets"]["delete"]["operationId"] == "clear_budget"
    assert paths["/api/spending/trends"]["get"]["operationId"] == "get_spending_trends"


@pytest.mark.asyncio
async def test_budget_settings_mcp_tool_delegates_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delegate the MCP budget-settings tool to the budget service."""
    budget_tools = sys.modules["lunchmoney_mcp.mcp.tools.budgets"]
    fetch_settings = AsyncMock(return_value=_budget_settings())
    monkeypatch.setattr(budget_tools, "fetch_budget_settings", fetch_settings)
    monkeypatch.setattr(budget_tools, "get_lunchmoney_app", object)

    await mcp.call_tool("get_budget_settings", {})

    fetch_settings.assert_awaited_once_with(client=ANY)


@pytest.mark.asyncio
async def test_sprint_four_mcp_tools_are_registered() -> None:
    """Publish budget mutations and spending trends through MCP."""
    tool_names = {tool.name for tool in await mcp.list_tools()}

    assert {"upsert_budget", "clear_budget", "get_spending_trends"} <= tool_names
