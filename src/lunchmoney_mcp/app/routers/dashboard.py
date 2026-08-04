"""Server-rendered financial dashboard endpoint."""

import datetime
import json
from pathlib import Path
from typing import Annotated

import jinja2
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from lunchmoney_mcp.app.dependencies import get_database, get_lunchmoney_app
from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney_mcp.services.dashboard import DashboardData, fetch_dashboard_data


router = APIRouter(tags=["Dashboard"])
"""FastAPI APIRouter for the authenticated financial dashboard."""

templates = Jinja2Templates(
    env=jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent.parent / "templates")),
        autoescape=jinja2.select_autoescape(["html"]),
        auto_reload=True,
        cache_size=0,
    ),
)
"""HTML templates used by dashboard routes."""


def _build_chart_data(dashboard_data: DashboardData) -> str | None:
    """Serialize category spending data for Frappe Charts rendering.

    Parameters
    ----------
    dashboard_data : DashboardData
        The composed dashboard data containing category spending.

    Returns
    -------
    str | None
        JSON string with labels and datasets, or ``None`` if no spending data exists.
    """
    spending = getattr(dashboard_data, "category_spending", None)
    if not spending or not spending.categories:
        return None

    expense_categories = [
        c
        for c in spending.categories
        if not getattr(c, "is_income", False)
        and (getattr(c, "total_amount", None) or 0)
    ]
    if not expense_categories:
        return None

    labels = [getattr(c, "category_name", "") for c in expense_categories]
    values = [abs(getattr(c, "total_amount", 0.0)) for c in expense_categories]

    return json.dumps({"labels": labels, "datasets": [{"values": values}]})


def _parse_period(period_raw: str | datetime.date | None) -> datetime.date | None:
    """Parse period query parameter into a date object.

    Parameters
    ----------
    period_raw : str | datetime.date | None
        Raw query parameter from query string.

    Returns
    -------
    datetime.date | None
        Parsed date object, or ``None`` if omitted or invalid.
    """
    if period_raw is None:
        return None
    if isinstance(period_raw, datetime.date):
        return period_raw
    try:
        if len(period_raw) == 7 and period_raw.count("-") == 1:
            return datetime.date.fromisoformat(f"{period_raw}-01")
        return datetime.date.fromisoformat(period_raw)
    except ValueError:
        return None


@router.get(
    path="/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def dashboard(
    request: Request,
    db: Annotated[LunchMoneyDatabase, Depends(dependency=get_database)],
    client: Annotated[LunchMoneyApp, Depends(dependency=get_lunchmoney_app)],
    period: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    """Render the authenticated, read-only Lunch Money dashboard for one month."""
    period_date = _parse_period(period)
    data = await fetch_dashboard_data(db=db, client=client, period_start=period_date)
    chart_data = _build_chart_data(data)
    is_hx_request = bool(
        request.headers.get("HX-Request") or request.headers.get("hx-request")
    )
    today = datetime.date.today()
    context = {
        "dashboard": data,
        "chart_data": chart_data,
        "is_hx_request": is_hx_request,
        "today": today,
    }

    if is_hx_request:
        target = (
            request.headers.get("HX-Target") or request.headers.get("hx-target") or ""
        ).lstrip("#")
        if target == "spending-workspace" or period:
            return templates.TemplateResponse(
                request=request,
                name="partials/_spending_workspace.html",
                context=context,
            )
        return templates.TemplateResponse(
            request=request,
            name="partials/cockpit_content.html",
            context=context,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=context,
    )


__all__ = ["router"]
