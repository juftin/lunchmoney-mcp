"""FastAPI dependencies for Lunch Money MCP."""

from collections.abc import AsyncIterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.config import get_secret_settings
from lunchmoney_mcp.database import LunchMoneyDatabase


@cache
def get_database() -> LunchMoneyDatabase:
    """FastAPI dependency supplying the shared cached LunchMoneyDatabase instance.

    Returns
    -------
    LunchMoneyDatabase
        Shared database access wrapper.
    """
    return LunchMoneyDatabase()


async def get_db_session(
    db: Annotated[LunchMoneyDatabase, Depends(dependency=get_database)],
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped AsyncSession.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Shared database instance supplied by dependency injection.

    Yields
    ------
    AsyncSession
        Request-scoped asynchronous database session.
    """
    async with db.session() as session:
        yield session


@cache
def get_lunchmoney_app() -> LunchMoneyApp:
    """FastAPI dependency supplying a cached LunchMoneyApp client instance.

    Returns
    -------
    LunchMoneyApp
        Configured Lunch Money API client.
    """
    return LunchMoneyApp(
        access_token=get_secret_settings().access_token,
        cache=False,
    )


__all__ = ["get_database", "get_db_session", "get_lunchmoney_app"]
