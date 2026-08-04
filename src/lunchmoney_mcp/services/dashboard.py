"""Read-only data composition for the server-rendered financial dashboard."""

import asyncio
import datetime
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar, cast

from lunchmoney.models import BudgetSettingsResponseObject, SummaryResponseObject

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney_mcp.database.models import SyncMetadata
from lunchmoney_mcp.schemas import (
    AccountsSummary,
    GroupedSpendingResponse,
    ScheduledSyncStatus,
    TransactionInfo,
)
from lunchmoney_mcp.services.accounts import fetch_accounts
from lunchmoney_mcp.services.budgets import fetch_budget_settings
from lunchmoney_mcp.services.spending import fetch_category_spending
from lunchmoney_mcp.services.summary import fetch_account_summary
from lunchmoney_mcp.services.sync import get_scheduled_sync_status
from lunchmoney_mcp.services.transactions import fetch_recent_transactions


ResultT = TypeVar("ResultT")
"""Type returned from one independently loaded dashboard section."""


@dataclass(frozen=True)
class DashboardData:
    """Read-only data rendered by the financial dashboard.

    Attributes
    ----------
    period_start : datetime.date
        First date included in the live budget summary.
    period_end : datetime.date
        Last date included in the live budget summary.
    previous_period_start : datetime.date
        First date of the previous calendar month for period navigation.
    next_period_start : datetime.date | None
        First date of the next calendar month, unless that month is in the future.
    transaction_last_synced_at : datetime.datetime | None
        Most recent persisted transaction-sync watermark.
    accounts : AccountsSummary | None
        Cached account summary, when it could be loaded.
    budget_summary : SummaryResponseObject | None
        Live budget summary, when the upstream request succeeded.
    budget_settings : BudgetSettingsResponseObject | None
        Live budget-period settings, when the upstream request succeeded.
    category_spending : GroupedSpendingResponse | None
        Cached category spending for the recent analysis window.
    transactions : list[TransactionInfo] | None
        Recent cached transactions, when available.
    scheduled_sync : ScheduledSyncStatus | None
        Last persisted scheduled-sync outcome, if one exists.
    unavailable_sections : tuple[str, ...]
        Safe labels for sections that could not be loaded.
    """

    period_start: datetime.date
    period_end: datetime.date
    previous_period_start: datetime.date
    next_period_start: datetime.date | None
    transaction_last_synced_at: datetime.datetime | None
    accounts: AccountsSummary | None
    budget_summary: SummaryResponseObject | None
    budget_settings: BudgetSettingsResponseObject | None
    category_spending: GroupedSpendingResponse | None
    transactions: list[TransactionInfo] | None
    scheduled_sync: ScheduledSyncStatus | None
    unavailable_sections: tuple[str, ...]


async def _capture(operation: Awaitable[ResultT]) -> ResultT | Exception:
    """Return an operation result while preserving a dashboard section failure."""
    try:
        return await operation
    except Exception as error:
        return error


def _available(
    result: ResultT | Exception,
    section_name: str,
    unavailable_sections: list[str],
) -> ResultT | None:
    """Return successful data and record a safe label for unavailable content."""
    if isinstance(result, Exception):
        unavailable_sections.append(section_name)
        return None
    return result


async def fetch_dashboard_data(
    db: LunchMoneyDatabase,
    client: LunchMoneyApp,
    period_start: datetime.date | None = None,
    transaction_limit: int = 10,
) -> DashboardData:
    """Load the independent dashboard sections without duplicating domain logic.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database used by cached account, spending, transaction, and sync queries.
    client : LunchMoneyApp
        Lunch Money client used by live summary and budget-setting queries.
    period_start : datetime.date | None
        Any date in the calendar month to render. Defaults to the current month.
    transaction_limit : int
        Maximum number of recent transactions to render.

    Returns
    -------
    DashboardData
        Data for every successfully loaded section plus safe unavailable-section labels.
    """
    today = datetime.date.today()
    resolved_period_start = min(period_start or today, today).replace(day=1)
    next_month_start = (
        resolved_period_start.replace(day=28) + datetime.timedelta(days=4)
    ).replace(day=1)
    period_end = min(next_month_start - datetime.timedelta(days=1), today)
    previous_period_start = (
        resolved_period_start - datetime.timedelta(days=1)
    ).replace(day=1)
    future_period_start = next_month_start if next_month_start <= today else None
    (
        sync_metadata_result,
        accounts_result,
        budget_summary_result,
        budget_settings_result,
        category_spending_result,
        transactions_result,
        scheduled_sync_result,
    ) = await asyncio.gather(
        _capture(db.get_sync_metadata("transactions")),
        _capture(fetch_accounts(db=db)),
        _capture(
            fetch_account_summary(
                client=client,
                start_date=resolved_period_start,
                end_date=period_end,
                include_totals=True,
            )
        ),
        _capture(fetch_budget_settings(client=client)),
        _capture(
            fetch_category_spending(
                db=db,
                start_date=resolved_period_start,
                end_date=period_end,
                days=None,
            )
        ),
        _capture(
            fetch_recent_transactions(
                db=db,
                limit=transaction_limit,
                start_date=resolved_period_start,
                end_date=period_end,
            )
        ),
        _capture(get_scheduled_sync_status(db=db)),
    )
    unavailable_sections: list[str] = []
    sync_metadata = _available(
        result=cast(SyncMetadata | Exception, sync_metadata_result),
        section_name="Cache freshness",
        unavailable_sections=unavailable_sections,
    )
    return DashboardData(
        period_start=resolved_period_start,
        period_end=period_end,
        previous_period_start=previous_period_start,
        next_period_start=future_period_start,
        transaction_last_synced_at=(
            sync_metadata.last_synced_at if sync_metadata is not None else None
        ),
        accounts=_available(
            result=cast(AccountsSummary | Exception, accounts_result),
            section_name="Account summary",
            unavailable_sections=unavailable_sections,
        ),
        budget_summary=_available(
            result=cast(SummaryResponseObject | Exception, budget_summary_result),
            section_name="Budget status",
            unavailable_sections=unavailable_sections,
        ),
        budget_settings=_available(
            result=cast(
                BudgetSettingsResponseObject | Exception,
                budget_settings_result,
            ),
            section_name="Budget settings",
            unavailable_sections=unavailable_sections,
        ),
        category_spending=_available(
            result=cast(
                GroupedSpendingResponse | Exception,
                category_spending_result,
            ),
            section_name="Category spending",
            unavailable_sections=unavailable_sections,
        ),
        transactions=_available(
            result=cast(list[TransactionInfo] | Exception, transactions_result),
            section_name="Recent transactions",
            unavailable_sections=unavailable_sections,
        ),
        scheduled_sync=_available(
            result=cast(ScheduledSyncStatus | None | Exception, scheduled_sync_result),
            section_name="Scheduled sync status",
            unavailable_sections=unavailable_sections,
        ),
        unavailable_sections=tuple(unavailable_sections),
    )


__all__ = ["DashboardData", "fetch_dashboard_data"]
