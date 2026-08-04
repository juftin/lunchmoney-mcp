"""FastAPI application for Lunch Money MCP."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastmcp.server.http import StarletteWithLifespan
from fastmcp.utilities.lifespan import combine_lifespans

from lunchmoney_mcp.app.auth import verify_api_key
from lunchmoney_mcp.app.lifespan import lifespan
from lunchmoney_mcp.app.security import apply_security_middleware
from lunchmoney_mcp.app.routers import (
    accounts_router,
    budgets_router,
    categories_router,
    dashboard_router,
    health_router,
    recurring_router,
    spending_router,
    summary_router,
    sync_router,
    tags_router,
    transactions_router,
    user_router,
)
from lunchmoney_mcp.logging_config import apply_logging_config
from lunchmoney_mcp.mcp import mcp
from lunchmoney_mcp.config import get_settings
from lunchmoney_mcp.observability import log_event, metrics

apply_logging_config()

logger: logging.Logger = logging.getLogger(__name__)

fastapi_app = FastAPI(
    title="Lunch Money MCP",
    description="Lunch Money Model Context Protocol Server & API",
    lifespan=lifespan,
)

fastapi_app.middleware("http")(verify_api_key)
fastapi_app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="dashboard_static",
)


async def observe_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a request ID and record safe request-level telemetry."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": "Internal server error"},
        )
    response.headers["X-Request-ID"] = request_id
    _record_request(
        request=request,
        request_id=request_id,
        status_code=status_code,
        duration_seconds=time.perf_counter() - started_at,
    )
    return response


def _record_request(
    request: Request,
    request_id: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record bounded metrics and a JSON log event for one completed request."""
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    is_mcp = request.url.path.startswith("/mcp")
    metrics.record_http_request(
        method=request.method,
        path=path,
        status_code=status_code,
        duration_seconds=duration_seconds,
        is_mcp=is_mcp,
    )
    log_event(
        logger,
        "http_request",
        request_id=request_id,
        method=request.method,
        path=path,
        status_code=status_code,
        duration_ms=round(duration_seconds * 1000, 3),
    )


fastapi_app.middleware("http")(observe_request)


fastapi_app.include_router(sync_router)
fastapi_app.include_router(health_router)
fastapi_app.include_router(user_router)
fastapi_app.include_router(summary_router)
fastapi_app.include_router(budgets_router)
fastapi_app.include_router(categories_router)
fastapi_app.include_router(dashboard_router)
fastapi_app.include_router(accounts_router)
fastapi_app.include_router(transactions_router)
fastapi_app.include_router(tags_router)
fastapi_app.include_router(recurring_router)
fastapi_app.include_router(spending_router)

mcp_app: StarletteWithLifespan = mcp.http_app(path="/mcp")
app = FastAPI(
    routes=[
        *mcp_app.routes,
        *fastapi_app.routes,
    ],
    lifespan=combine_lifespans(mcp_app.lifespan, lifespan),
)

app.middleware("http")(verify_api_key)
app.middleware("http")(observe_request)
apply_security_middleware(app=app, settings=get_settings())

__all__: list[str] = [
    "app",
    "fastapi_app",
    "mcp",
    "mcp_app",
]

if __name__ == "__main__":
    mcp.run()
