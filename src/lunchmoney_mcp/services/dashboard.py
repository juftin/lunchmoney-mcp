"""Read-only data composition for the server-rendered financial dashboard."""

import asyncio
import datetime
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar, cast

from apscheduler.triggers.cron import CronTrigger
from lunchmoney.models import (
    BudgetSettingsResponseObject,
    SummaryResponseObject,
    TransactionObject,
)

from sqlalchemy.engine import make_url

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.config import (
    IN_MEMORY_DATABASE_URL,
    get_secret_settings,
    get_settings,
)
from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney_mcp.database.models import SyncMetadata
from lunchmoney_mcp.schemas import (
    AccountsSummary,
    GroupedSpendingResponse,
    ScheduledSyncStatus,
    SyncStatusSummary,
)
from lunchmoney_mcp.services.accounts import fetch_accounts
from lunchmoney_mcp.services.budgets import fetch_budget_settings
from lunchmoney_mcp.services.spending import fetch_category_spending
from lunchmoney_mcp.services.summary import fetch_account_summary
from lunchmoney_mcp.services.sync import get_scheduled_sync_status
from lunchmoney_mcp.services.transactions import fetch_recent_transactions

logger = logging.getLogger(__name__)


ResultT = TypeVar("ResultT")
"""Type returned from one independently loaded dashboard section."""


def humanize_time_ago(
    dt: datetime.datetime | None,
    now: datetime.datetime | None = None,
) -> str:
    """Return a human-friendly relative time string (e.g. '21 hours ago', '5 minutes ago', 'just now')."""
    if dt is None:
        return "Not yet synced"
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    diff_seconds = int((now - dt).total_seconds())
    if diff_seconds < 0:
        diff_seconds = 0

    if diff_seconds < 60:
        return "just now"
    minutes = diff_seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


def _normalize_cron(raw: str | None) -> str | None:
    """Normalize cron string and return None if disabled or empty."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if cleaned in {"", "none", "disabled", "false", "0", "null", "off"}:
        return None
    return raw.strip()


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
    transactions : list[TransactionObject] | None
        Recent cached transactions, when available.
    scheduled_sync : ScheduledSyncStatus | None
        Last persisted scheduled-sync outcome, if one exists.
    sync_status : SyncStatusSummary | None
        Composition of persistence mode, sync schedules, and next run estimates.
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
    transactions: list[TransactionObject] | None
    scheduled_sync: ScheduledSyncStatus | None
    sync_status: SyncStatusSummary | None
    unavailable_sections: tuple[str, ...]


async def _capture(operation: Awaitable[ResultT]) -> ResultT | Exception:
    """Safely capture exceptions from concurrent dashboard data tasks."""
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
        logger.warning(
            "Dashboard section '%s' unavailable: %s",
            section_name,
            result,
            exc_info=result,
        )
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
        metadata_sync_result,
        accounts_result,
        budget_summary_result,
        budget_settings_result,
        category_spending_result,
        transactions_result,
        scheduled_sync_result,
        db_stats_result,
    ) = await asyncio.gather(
        _capture(db.get_sync_metadata("transactions")),
        _capture(db.get_sync_metadata("metadata")),
        _capture(fetch_accounts(db=db)),
        _capture(
            fetch_account_summary(
                client=client,
                start_date=resolved_period_start,
                end_date=period_end,
                db=db,
                include_totals=True,
            )
        ),
        _capture(fetch_budget_settings(client=client, db=db)),
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
        _capture(db.get_database_stats()),
    )
    unavailable_sections: list[str] = []
    sync_metadata = _available(
        result=cast(SyncMetadata | Exception, sync_metadata_result),
        section_name="Cache freshness",
        unavailable_sections=unavailable_sections,
    )
    metadata_sync = _available(
        result=cast(SyncMetadata | Exception, metadata_sync_result),
        section_name="Metadata sync status",
        unavailable_sections=unavailable_sections,
    )
    scheduled_sync = _available(
        result=cast(ScheduledSyncStatus | None | Exception, scheduled_sync_result),
        section_name="Scheduled sync status",
        unavailable_sections=unavailable_sections,
    )
    db_stats_raw = _available(
        result=cast(dict[str, int] | Exception, db_stats_result),
        section_name="Database stats",
        unavailable_sections=unavailable_sections,
    )
    db_stats = db_stats_raw if isinstance(db_stats_raw, dict) else {}

    settings = get_settings()
    secret_settings = get_secret_settings()

    if settings.stateless:
        persistence_mode = "Stateless (In-Memory)"
        raw_db_url = IN_MEMORY_DATABASE_URL
    else:
        raw_db_url = secret_settings.database_url
        if secret_settings.database_url.startswith("postgresql"):
            persistence_mode = "Persistent (PostgreSQL)"
        elif secret_settings.database_url.startswith("sqlite"):
            persistence_mode = "Persistent (SQLite)"
        else:
            persistence_mode = "Persistent"

    try:
        db_url = make_url(raw_db_url).render_as_string(hide_password=True)
    except Exception:
        db_url = raw_db_url

    db_driver = db_url.split("://")[0]

    last_synced_at = sync_metadata.last_synced_at if sync_metadata is not None else None
    metadata_last_synced_at = (
        metadata_sync.last_synced_at if metadata_sync is not None else last_synced_at
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    transaction_cron = _normalize_cron(
        settings.schedule_transactions_cron or settings.schedule_cron
    )
    metadata_cron = _normalize_cron(settings.schedule_metadata_cron)

    transaction_next_sync_at: datetime.datetime | None = None
    if transaction_cron:
        try:
            trigger = CronTrigger.from_crontab(
                transaction_cron,
                timezone=settings.schedule_timezone,
            )
            transaction_next_sync_at = trigger.get_next_fire_time(None, now)
        except Exception:
            transaction_next_sync_at = None

    metadata_next_sync_at: datetime.datetime | None = None
    if metadata_cron:
        try:
            trigger = CronTrigger.from_crontab(
                metadata_cron,
                timezone=settings.schedule_timezone,
            )
            metadata_next_sync_at = trigger.get_next_fire_time(None, now)
        except Exception:
            metadata_next_sync_at = None

    sync_status = SyncStatusSummary(
        persistence_mode=persistence_mode,
        db_driver=db_driver,
        db_url=db_url,
        stored_transactions=db_stats.get("transactions", 0),
        stored_categories=db_stats.get("categories", 0),
        stored_accounts=db_stats.get("accounts", 0),
        stored_tags=db_stats.get("tags", 0),
        transaction_cron=transaction_cron,
        transaction_timezone=settings.schedule_timezone,
        transaction_last_synced_at=last_synced_at,
        transaction_next_sync_at=transaction_next_sync_at,
        metadata_cron=metadata_cron,
        metadata_timezone=settings.schedule_timezone,
        metadata_last_synced_at=metadata_last_synced_at,
        metadata_next_sync_at=metadata_next_sync_at,
        last_synced_at=last_synced_at,
        schedule_cron=transaction_cron,
        schedule_timezone=settings.schedule_timezone,
        next_sync_at=transaction_next_sync_at,
        embed_scheduler=settings.embed_scheduler,
        scheduled_sync=scheduled_sync,
    )

    return DashboardData(
        period_start=resolved_period_start,
        period_end=period_end,
        previous_period_start=previous_period_start,
        next_period_start=future_period_start,
        transaction_last_synced_at=last_synced_at,
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
            result=cast(list[TransactionObject] | Exception, transactions_result),
            section_name="Recent transactions",
            unavailable_sections=unavailable_sections,
        ),
        scheduled_sync=scheduled_sync,
        sync_status=sync_status,
        unavailable_sections=tuple(unavailable_sections),
    )


__all__ = ["DashboardData", "fetch_dashboard_data"]
