"""Tests for the vendored Lunch Money application module."""

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import ANY, AsyncMock, create_autospec

import sys
import pytest
from lunchmoney_mcp.app import app as fastapi_app
from lunchmoney_mcp import client as app_module

app_main_module = sys.modules["lunchmoney_mcp.app.main"]
lifespan_module = sys.modules["lunchmoney_mcp.app.lifespan"]


def create_app(
    monkeypatch: pytest.MonkeyPatch, *, cache: bool = True
) -> app_module.LunchMoneyApp:
    """Create an initialized app with its network client patched out."""
    monkeypatch.setattr(app_module, "LunchableClient", lambda **kwargs: object())
    return app_module.LunchMoneyApp(access_token="token", cache=cache)


if TYPE_CHECKING:

    async def assert_refresh_overload_types(app: app_module.LunchMoneyApp) -> None:
        """Type-check model-specific refresh return values."""
        user: app_module.UserObject = await app.refresh(app_module.UserObject)
        transactions: dict[int, app_module.TransactionObject] = await app.refresh(
            app_module.TransactionObject
        )
        categories: dict[int, app_module.CategoryObject] = await app.refresh(
            app_module.CategoryObject
        )

        assert user
        assert transactions
        assert categories


def test_vendored_app_exports_lunch_money_app() -> None:
    """Expose the upstream application class from the package module."""
    from lunchmoney_mcp.client import LunchMoneyApp

    assert LunchMoneyApp.__name__ == "LunchMoneyApp"


def test_app_initializes_instance_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store the constructor cache setting on each application instance."""
    app = create_app(monkeypatch, cache=False)

    assert app.cache is False


@pytest.mark.asyncio
async def test_refresh_without_cache_does_not_replace_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return refreshed categories without replacing the cached categories."""
    from lunchmoney_mcp.client import (
        CategoryObject,
        _ObjectMapper,
    )

    category = SimpleNamespace(id=1)

    async def get_all_categories(**kwargs: object) -> SimpleNamespace:
        """Return one known category response."""
        return SimpleNamespace(categories=[category])

    app = create_app(monkeypatch)
    monkeypatch.setattr(
        app_module.LunchMoneyApp,
        "_model_mapping",
        {
            CategoryObject: _ObjectMapper(
                func=get_all_categories,
                data_attr="categories",
            )
        },
    )
    result = await app.refresh(CategoryObject, cache=False)

    assert result == {1: category}
    assert app.data.categories == {}


@pytest.mark.asyncio
async def test_refresh_data_forwards_cache_to_each_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward the cache control to every requested model refresh."""
    from lunchmoney_mcp.client import CategoryObject

    app = create_app(monkeypatch)
    app.refresh = AsyncMock()

    await app.refresh_data(models=[CategoryObject], cache=False)

    app.refresh.assert_awaited_once_with(CategoryObject, cache=False)


@pytest.mark.asyncio
async def test_refresh_data_inherits_cache_from_app_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve an omitted bulk-refresh cache setting from the instance."""
    from lunchmoney_mcp.client import CategoryObject

    app = create_app(monkeypatch, cache=False)
    app.refresh = AsyncMock()

    await app.refresh_data(models=[CategoryObject])

    app.refresh.assert_awaited_once_with(CategoryObject, cache=False)


@pytest.mark.asyncio
async def test_refresh_transactions_without_cache_does_not_update_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return refreshed transactions without updating the cached transactions."""

    transaction = SimpleNamespace(id=1)

    async def paginate_transactions(
        self: app_module.LunchMoneyApp, **kwargs: object
    ) -> object:
        """Yield one known transaction."""
        yield transaction

    app = create_app(monkeypatch)
    monkeypatch.setattr(
        app_module.LunchMoneyApp,
        "_paginate_transactions",
        paginate_transactions,
    )

    result = await app.refresh_transactions(cache=False)

    assert result == {1: transaction}
    assert app.data.transactions == {}


@pytest.mark.asyncio
async def test_refresh_inherits_cache_from_app_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use an instance cache default when refresh cache is omitted."""
    from lunchmoney_mcp.client import (
        CategoryObject,
        _ObjectMapper,
    )

    category = SimpleNamespace(id=1)

    async def get_all_categories(**kwargs: object) -> SimpleNamespace:
        """Return one known category response."""
        return SimpleNamespace(categories=[category])

    app = create_app(monkeypatch, cache=False)
    monkeypatch.setattr(
        app_module.LunchMoneyApp,
        "_model_mapping",
        {
            CategoryObject: _ObjectMapper(
                func=get_all_categories,
                data_attr="categories",
            )
        },
    )
    result = await app.refresh(CategoryObject)

    assert result == {1: category}
    assert app.data.categories == {}


@pytest.mark.asyncio
async def test_refresh_transactions_inherits_cache_from_app_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use an instance cache default when transaction cache is omitted."""

    transaction = SimpleNamespace(id=1)

    async def paginate_transactions(
        self: app_module.LunchMoneyApp, **kwargs: object
    ) -> object:
        """Yield one known transaction."""
        yield transaction

    app = create_app(monkeypatch, cache=False)
    monkeypatch.setattr(
        app_module.LunchMoneyApp,
        "_paginate_transactions",
        paginate_transactions,
    )

    result = await app.refresh_transactions()

    assert result == {1: transaction}
    assert app.data.transactions == {}


def test_sync_summary_total() -> None:
    """Calculate total synced records across entity types."""
    summary = app_module.SyncSummary(
        user=1,
        plaid_accounts=2,
        manual_accounts=1,
        categories=5,
        tags=3,
        transactions=10,
    )
    assert summary.total == 22


@pytest.mark.asyncio
async def test_sync_database_populates_last_30_days(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fetch 30-day window objects and persist them into database."""
    import datetime
    from lunchmoney_mcp.database import LunchMoneyDatabase
    from lunchmoney_mcp.database.models import Transaction, User
    from database.factories import (
        category_object,
        plaid_account_object,
        transaction_object,
        user_object,
    )

    api_user = user_object()
    api_plaid = plaid_account_object()
    api_category = category_object()
    api_txn = transaction_object(transaction_id=101, tag_ids=[])

    app = create_app(monkeypatch)

    async def mock_refresh(self: app_module.LunchMoneyApp, model: Any) -> Any:
        if model is app_module.UserObject:
            return api_user
        if model is app_module.PlaidAccountObject:
            return {api_plaid.id: api_plaid}
        if model is app_module.CategoryObject:
            return {api_category.id: api_category}
        return {}

    async def mock_refresh_txns(
        self: app_module.LunchMoneyApp,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        **kwargs: Any,
    ) -> dict[int, app_module.TransactionObject]:
        assert start_date is not None
        assert end_date is not None
        assert (end_date - start_date).days == 30
        return {101: api_txn}

    monkeypatch.setattr(app_module.LunchMoneyApp, "refresh", mock_refresh)
    monkeypatch.setattr(
        app_module.LunchMoneyApp, "refresh_transactions", mock_refresh_txns
    )

    db_path = tmp_path / "sync.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    async with LunchMoneyDatabase(db_url) as db:
        # Create schema tables for the test DB
        async with db.engine.begin() as conn:
            from sqlmodel import SQLModel

            await conn.run_sync(SQLModel.metadata.create_all)

        from lunchmoney_mcp.app import sync_database

        summary = await sync_database(db=db, client=app, days=30)

        assert summary.user == 1
        assert summary.plaid_accounts == 1
        assert summary.categories == 1
        assert summary.transactions == 1
        assert summary.total == 4

        db_user = await db.get(User, 1)
        assert db_user is not None
        assert db_user.name == "Synthetic User"

        db_txn = await db.get(Transaction, 101)
        assert db_txn is not None
        assert db_txn.payee == "Synthetic Parent Payee"


def test_fastapi_sync_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trigger migrations and sync via the /sync endpoint."""
    from starlette.testclient import TestClient

    migrations_ran = False

    async def mock_migrations(database_url: str | None = None) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    async def mock_sync(
        client: Any,
        db: Any,
        days: int = 30,
        incremental: bool = False,
        safety_margin_minutes: int | None = None,
    ) -> app_module.SyncSummary:
        assert incremental is False
        assert safety_margin_minutes is None
        return app_module.SyncSummary(user=1, transactions=5)

    import lunchmoney_mcp.services.sync as sync_service_module

    monkeypatch.setattr(sync_service_module, "run_migrations", mock_migrations)
    monkeypatch.setattr(sync_service_module, "sync_database", mock_sync)
    monkeypatch.setattr(app_module, "LunchableClient", lambda **kwargs: object())
    monkeypatch.setenv("LUNCHMONEY_ACCESS_TOKEN", "mock-token")

    with TestClient(fastapi_app, base_url="http://localhost") as client:
        response = client.post("/sync?days=30")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Synchronization complete"
        assert data["synced"]["user"] == 1
        assert data["synced"]["transactions"] == 5
        assert migrations_ran is True


def test_fastapi_sync_endpoint_forwards_incremental_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward incremental query controls unchanged to the sync service."""
    from lunchmoney_mcp.schemas import SyncDetails, SyncResponse
    from starlette.testclient import TestClient

    sync_router_module = sys.modules["lunchmoney_mcp.app.routers.sync"]
    mock_execute_sync = AsyncMock(
        return_value=SyncResponse(
            synced=SyncDetails(
                user=0,
                plaid_accounts=0,
                manual_accounts=0,
                categories=0,
                tags=0,
                transactions=0,
                total=0,
            )
        )
    )
    monkeypatch.setattr(sync_router_module, "execute_sync", mock_execute_sync)
    monkeypatch.setattr(app_module, "LunchableClient", lambda **kwargs: object())
    monkeypatch.setenv("LUNCHMONEY_ACCESS_TOKEN", "mock-token")

    with TestClient(fastapi_app, base_url="http://localhost") as client:
        response = client.post("/sync?days=14&incremental=true&safety_margin_minutes=9")

    assert response.status_code == 200
    mock_execute_sync.assert_awaited_once_with(
        db=ANY,
        client=ANY,
        days=14,
        incremental=True,
        safety_margin_minutes=9,
    )


@pytest.mark.asyncio
async def test_execute_sync_forwards_incremental_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward incremental controls from the shared service to sync policy."""
    from lunchmoney_mcp.client import LunchMoneyApp, SyncSummary
    from lunchmoney_mcp.database import LunchMoneyDatabase
    import lunchmoney_mcp.services.sync as sync_service_module

    database = create_autospec(LunchMoneyDatabase, instance=True)
    database.is_stateless = False
    client = create_autospec(LunchMoneyApp, instance=True)
    sync_database_mock = AsyncMock(return_value=SyncSummary())
    monkeypatch.setattr(sync_service_module, "run_migrations", AsyncMock())
    monkeypatch.setattr(sync_service_module, "sync_database", sync_database_mock)

    await sync_service_module.execute_sync(
        db=database,
        client=client,
        days=45,
        incremental=True,
        safety_margin_minutes=7,
    )

    sync_database_mock.assert_awaited_once_with(
        db=database,
        client=client,
        days=45,
        incremental=True,
        safety_margin_minutes=7,
    )


@pytest.mark.asyncio
async def test_explicit_sync_initializes_and_persists_to_stateless_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Create the in-memory schema during sync when startup has not run."""
    from database.factories import user_object
    from lunchmoney_mcp.client import (
        CategoryObject,
        LunchMoneyApp,
        ManualAccountObject,
        PlaidAccountObject,
        TagObject,
        UserObject,
    )
    from lunchmoney_mcp.config import get_settings
    from lunchmoney_mcp.database import LunchMoneyDatabase, User
    from lunchmoney_mcp.services.sync import execute_sync

    async def refresh(model: type[Any]) -> Any:
        """Return a synthetic user and empty collections for other domains."""
        if model is UserObject:
            return user_object()
        if model in {
            PlaidAccountObject,
            ManualAccountObject,
            CategoryObject,
            TagObject,
        }:
            return {}
        raise AssertionError(f"Unexpected model refresh: {model}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATELESS", "true")
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    client = AsyncMock(spec=LunchMoneyApp)
    client.refresh.side_effect = refresh
    client.refresh_transactions.return_value = {}

    try:
        async with LunchMoneyDatabase() as database:
            response = await execute_sync(db=database, client=client)
            persisted_user = await database.get(User, 1)

        assert response.synced.user == 1
        assert persisted_user is not None
        assert persisted_user.name == "Synthetic User"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_execute_mcp_sync_forwards_incremental_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forward incremental controls through the MCP-facing shared service."""
    from lunchmoney_mcp.client import LunchMoneyApp
    from lunchmoney_mcp.database import LunchMoneyDatabase
    from lunchmoney_mcp.schemas import SyncDetails, SyncResponse
    import lunchmoney_mcp.services.sync as sync_service_module

    database = create_autospec(LunchMoneyDatabase, instance=True)
    client = create_autospec(LunchMoneyApp, instance=True)
    execute_sync_mock = AsyncMock(
        return_value=SyncResponse(
            message="Synchronization complete",
            synced=SyncDetails(
                user=0,
                plaid_accounts=0,
                manual_accounts=0,
                categories=0,
                tags=0,
                transactions=0,
                total=0,
            ),
        )
    )
    monkeypatch.setattr(sync_service_module, "execute_sync", execute_sync_mock)

    await sync_service_module.execute_mcp_sync(
        db=database,
        client=client,
        days=45,
        incremental=True,
        safety_margin_minutes=7,
    )

    execute_sync_mock.assert_awaited_once_with(
        db=database,
        client=client,
        days=45,
        incremental=True,
        safety_margin_minutes=7,
    )


@pytest.mark.asyncio
async def test_fastapi_database_dependencies(tmp_path: Path) -> None:
    """Verify get_database and get_db_session dependencies yield expected instances."""
    from lunchmoney_mcp.app import get_database, get_db_session
    from lunchmoney_mcp.database import LunchMoneyDatabase
    from sqlmodel.ext.asyncio.session import AsyncSession

    db_instance = get_database()
    assert isinstance(db_instance, LunchMoneyDatabase)

    db_path = tmp_path / "dep.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    async with LunchMoneyDatabase(db_url) as test_db:
        sessions: list[AsyncSession] = []
        async for session in get_db_session(test_db):
            sessions.append(session)

        assert len(sessions) == 1
        assert isinstance(sessions[0], AsyncSession)


def test_fastapi_lifespan_migration_single_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify lifespan runs database migrations when filelock is acquired."""
    from starlette.testclient import TestClient

    migrations_ran = False

    async def mock_migrations(database_url: str | None = None) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    monkeypatch.setattr(lifespan_module, "run_migrations", mock_migrations)

    with TestClient(fastapi_app, base_url="http://localhost") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert migrations_ran is True


def test_stateless_startup_syncs_and_persists_without_manual_schema_setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Initialize the cached stateless schema before real sync persistence."""
    from lunchmoney_mcp.app.dependencies import get_database
    from lunchmoney_mcp.client import (
        CategoryObject,
        ManualAccountObject,
        PlaidAccountObject,
        TagObject,
        UserObject,
    )
    from lunchmoney_mcp.config import get_settings
    from starlette.testclient import TestClient
    from database.factories import user_object

    async def mock_refresh(
        self: app_module.LunchMoneyApp,
        model: type[Any],
    ) -> Any:
        """Return a synthetic user and empty collections for other domains."""
        if model is UserObject:
            return user_object()
        if model in {
            PlaidAccountObject,
            ManualAccountObject,
            CategoryObject,
            TagObject,
        }:
            return {}
        raise AssertionError(f"Unexpected model refresh: {model}")

    async def mock_refresh_transactions(
        self: app_module.LunchMoneyApp,
        **kwargs: Any,
    ) -> dict[int, Any]:
        """Return no transactions while exercising the real sync service."""
        return {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STATELESS", "true")
    monkeypatch.setenv("LUNCHMONEY_ACCESS_TOKEN", "mock-token")
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    monkeypatch.setattr(app_module, "LunchableClient", lambda **kwargs: object())
    monkeypatch.setattr(app_module.LunchMoneyApp, "refresh", mock_refresh)
    monkeypatch.setattr(
        app_module.LunchMoneyApp,
        "refresh_transactions",
        mock_refresh_transactions,
    )
    get_settings.cache_clear()
    get_database.cache_clear()

    try:
        with TestClient(fastapi_app, base_url="http://localhost") as client:
            empty_user = client.get("/user")
            sync_response = client.post("/sync?days=30")
            persisted_user = client.get("/user")

        assert empty_user.status_code == 200
        assert empty_user.json() is None
        assert sync_response.status_code == 200
        assert sync_response.json()["synced"]["user"] == 1
        assert persisted_user.status_code == 200
        assert persisted_user.json()["name"] == "Synthetic User"
    finally:
        get_settings.cache_clear()
        get_database.cache_clear()
