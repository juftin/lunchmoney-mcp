"""Service logic for live Lunch Money budget settings queries."""

import datetime

from lunchmoney.models import (
    BudgetSettingsResponseObject,
    BudgetUpsertResponseObject,
    UpsertBudgetRequestObject,
)

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase


async def fetch_budget_settings(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase | None = None,
    force_refresh: bool = False,
) -> BudgetSettingsResponseObject:
    """Fetch the authenticated user's budget-period settings.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    db : LunchMoneyDatabase | None
        Optional database instance containing persisted sync metadata.
    force_refresh : bool
        Whether to bypass client cache and force an upstream API call.

    Returns
    -------
    BudgetSettingsResponseObject
        Upstream budget-period settings.
    """
    if not force_refresh:
        if db is not None:
            meta = await db.get_sync_metadata("budget_settings")
            if meta and meta.payload:
                return BudgetSettingsResponseObject.model_validate(meta.payload)
        if client.data.budget_settings is not None:
            return client.data.budget_settings
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

    res = await client.client.budgets.get_budget_settings()
    client.data.budget_settings = res
    return res


async def set_budget_value(
    client: LunchMoneyApp,
    request: UpsertBudgetRequestObject,
) -> BudgetUpsertResponseObject:
    """Set a category's budget value for one budget period upstream.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    request : UpsertBudgetRequestObject
        Validated category, period, amount, and optional currency or notes.

    Returns
    -------
    BudgetUpsertResponseObject
        Canonical budget value returned by Lunch Money.
    """
    res = await client.client.budgets.upsert_budget(
        upsert_budget_request_object=request,
    )
    client.data.summaries.clear()
    return res


async def clear_budget_value(
    client: LunchMoneyApp,
    category_id: int,
    start_date: datetime.date,
) -> None:
    """Clear a category's budget value for one budget period upstream.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    category_id : int
        Identifier of the budget category to clear.
    start_date : datetime.date
        Start date of the budget period to clear.
    """
    await client.client.budgets.delete_budget(
        category_id=category_id,
        start_date=start_date,
    )
    client.data.summaries.clear()
