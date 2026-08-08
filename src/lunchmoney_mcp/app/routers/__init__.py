"""FastAPI router package containing domain-specific API endpoints."""

from lunchmoney_mcp.app.routers.accounts import router as accounts_router
from lunchmoney_mcp.app.routers.budgets import router as budgets_router
from lunchmoney_mcp.app.routers.categories import router as categories_router
from lunchmoney_mcp.app.routers.dashboard import router as dashboard_router
from lunchmoney_mcp.app.routers.health import router as health_router
from lunchmoney_mcp.app.routers.recurring import router as recurring_router
from lunchmoney_mcp.app.routers.spending import router as spending_router
from lunchmoney_mcp.app.routers.summary import router as summary_router
from lunchmoney_mcp.app.routers.sync import router as sync_router
from lunchmoney_mcp.app.routers.tags import router as tags_router
from lunchmoney_mcp.app.routers.transactions import router as transactions_router
from lunchmoney_mcp.app.routers.user import router as user_router

__all__ = [
    "accounts_router",
    "budgets_router",
    "categories_router",
    "dashboard_router",
    "health_router",
    "recurring_router",
    "spending_router",
    "summary_router",
    "sync_router",
    "tags_router",
    "transactions_router",
    "user_router",
]
