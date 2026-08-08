"""Service logic for live Lunch Money budget summary queries."""

import datetime

from lunchmoney.models import SummaryResponseObject

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase


async def fetch_account_summary(
    client: LunchMoneyApp,
    start_date: datetime.date,
    end_date: datetime.date,
    db: LunchMoneyDatabase | None = None,
    include_exclude_from_budgets: bool | None = None,
    include_occurrences: bool | None = None,
    include_past_budget_dates: bool | None = None,
    include_totals: bool | None = None,
    include_rollover_pool: bool | None = None,
    force_refresh: bool = False,
) -> SummaryResponseObject:
    """Fetch a live budget summary for a specified date range.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    start_date : datetime.date
        Inclusive start of the requested budget range.
    end_date : datetime.date
        Inclusive end of the requested budget range.
    db : LunchMoneyDatabase | None
        Optional database instance containing persisted sync metadata.
    include_exclude_from_budgets : bool | None
        Whether excluded categories should be included.
    include_occurrences : bool | None
        Whether category budget occurrences should be included.
    include_past_budget_dates : bool | None
        Whether prior occurrences should be included with occurrences.
    include_totals : bool | None
        Whether top-level inflow and outflow totals should be included.
    include_rollover_pool : bool | None
        Whether rollover-pool details should be included.
    force_refresh : bool
        Whether to bypass client cache and force an upstream API call.

    Returns
    -------
    SummaryResponseObject
        Upstream budget summary response for the requested range.
    """
    cache_key = (
        start_date,
        end_date,
        include_exclude_from_budgets,
        include_occurrences,
        include_past_budget_dates,
        include_totals,
        include_rollover_pool,
    )
    if not force_refresh:
        if db is not None:
            meta = await db.get_sync_metadata("summary")
            if meta and meta.payload:
                return SummaryResponseObject.model_validate(meta.payload)
        if cache_key in client.data.summaries:
            return client.data.summaries[cache_key]
        for (st, en, *rest), summary in client.data.summaries.items():
            if st == start_date and en == end_date:
                return summary
        return SummaryResponseObject.model_validate({"aligned": True, "categories": []})

    res = await client.client.summary.get_budget_summary(
        start_date=start_date,
        end_date=end_date,
        include_exclude_from_budgets=include_exclude_from_budgets,
        include_occurrences=include_occurrences,
        include_past_budget_dates=include_past_budget_dates,
        include_totals=include_totals,
        include_rollover_pool=include_rollover_pool,
    )
    client.data.summaries[cache_key] = res
    return res
