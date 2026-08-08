"""Integration tests for incremental synchronization metadata."""

import datetime
import importlib
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from lunchmoney_mcp.app.sync import sync_database
from lunchmoney_mcp.client import LunchMoneyApp, UserObject
from lunchmoney_mcp.database import LunchMoneyDatabase, SyncMetadata, run_migrations


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[LunchMoneyDatabase]:
    """Provide a fresh migrated database for incremental metadata tests."""
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'incremental-sync.db'}"
    await run_migrations(database_url)
    async with LunchMoneyDatabase(database_url) as test_database:
        yield test_database


@pytest.fixture
def client() -> AsyncMock:
    """Provide a client double with successful empty domain refreshes."""
    from database.factories import user_object
    from lunchmoney_mcp.client import LunchableData

    test_client = AsyncMock(spec=LunchMoneyApp)
    test_client.data = LunchableData()

    async def refresh(model: type[Any]) -> Any:
        """Return the required user object and empty collection domains."""
        if model is UserObject:
            return user_object()
        return {}

    test_client.refresh.side_effect = refresh
    test_client.refresh_transactions.return_value = {}
    return test_client


@pytest.mark.asyncio
async def test_sync_metadata_is_upserted_by_domain(
    database: LunchMoneyDatabase,
) -> None:
    """Replace and reload the watermark identified by one domain."""
    timestamp = datetime.datetime(2026, 7, 28, tzinfo=datetime.timezone.utc)
    stored = await database.upsert_sync_metadata(
        SyncMetadata(domain="transactions", last_synced_at=timestamp)
    )
    assert stored.last_synced_at == timestamp
    assert (await database.get_sync_metadata("transactions")) == stored


@pytest.mark.asyncio
async def test_sync_metadata_upsert_replaces_domain_watermark(
    database: LunchMoneyDatabase,
) -> None:
    """Replace the previous watermark when the domain already exists."""
    original = SyncMetadata(
        domain="transactions",
        last_synced_at=datetime.datetime(2026, 7, 27, tzinfo=datetime.timezone.utc),
    )
    replacement = SyncMetadata(
        domain="transactions",
        last_synced_at=datetime.datetime(2026, 7, 28, tzinfo=datetime.timezone.utc),
    )

    await database.upsert_sync_metadata(original)
    stored = await database.upsert_sync_metadata(replacement)

    assert stored.last_synced_at == replacement.last_synced_at
    assert (await database.get_sync_metadata("transactions")) == replacement


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (
            datetime.datetime(2026, 7, 28, 10, 0),
            datetime.datetime(2026, 7, 28, 10, 0, tzinfo=datetime.timezone.utc),
        ),
        (
            datetime.datetime(
                2026,
                7,
                28,
                10,
                0,
                tzinfo=datetime.timezone(datetime.timedelta(hours=-6)),
            ),
            datetime.datetime(2026, 7, 28, 16, 0, tzinfo=datetime.timezone.utc),
        ),
    ],
)
@pytest.mark.asyncio
async def test_sync_metadata_normalizes_watermarks_to_utc(
    database: LunchMoneyDatabase,
    timestamp: datetime.datetime,
    expected: datetime.datetime,
) -> None:
    """Normalize naive and offset-aware watermarks before persistence."""
    metadata = SyncMetadata(domain="transactions", last_synced_at=timestamp)

    assert metadata.last_synced_at == expected
    assert metadata.last_synced_at.tzinfo is datetime.timezone.utc

    stored = await database.upsert_sync_metadata(metadata)

    assert stored.last_synced_at == expected
    assert stored.last_synced_at.tzinfo is datetime.timezone.utc
    assert (await database.get_sync_metadata("transactions")) == stored


@pytest.mark.asyncio
async def test_incremental_sync_subtracts_requested_safety_margin(
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Query from the stored watermark minus an explicit overlap margin."""
    watermark = datetime.datetime(2026, 7, 28, 12, 0, tzinfo=datetime.timezone.utc)
    await database.upsert_sync_metadata(
        SyncMetadata(domain="transactions", last_synced_at=watermark)
    )

    await sync_database(
        db=database,
        client=cast(LunchMoneyApp, client),
        incremental=True,
        safety_margin_minutes=7,
    )

    client.refresh_transactions.assert_awaited_once_with(
        updated_since=watermark - datetime.timedelta(minutes=7),
        cache=False,
    )


@pytest.mark.asyncio
async def test_incremental_sync_uses_configured_safety_margin(
    monkeypatch: pytest.MonkeyPatch,
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Use the configured overlap when the request omits an override."""
    sync_module = importlib.import_module("lunchmoney_mcp.app.sync")

    watermark = datetime.datetime(2026, 7, 28, 12, 0, tzinfo=datetime.timezone.utc)
    await database.upsert_sync_metadata(
        SyncMetadata(domain="transactions", last_synced_at=watermark)
    )
    monkeypatch.setattr(
        sync_module,
        "get_settings",
        lambda: SimpleNamespace(sync_safety_margin_minutes=11),
    )

    await sync_database(
        db=database,
        client=cast(LunchMoneyApp, client),
        incremental=True,
    )

    client.refresh_transactions.assert_awaited_once_with(
        updated_since=watermark - datetime.timedelta(minutes=11),
        cache=False,
    )


@pytest.mark.asyncio
async def test_incremental_sync_without_watermark_uses_date_range(
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Fall back to the requested date window before a watermark exists."""
    start_date = datetime.date(2026, 6, 1)
    end_date = datetime.date(2026, 7, 1)

    await sync_database(
        db=database,
        client=cast(LunchMoneyApp, client),
        start_date=start_date,
        end_date=end_date,
        incremental=True,
    )

    client.refresh_transactions.assert_awaited_once_with(
        start_date=start_date,
        end_date=end_date,
        cache=False,
    )


@pytest.mark.asyncio
async def test_successful_incremental_sync_creates_watermark_after_upsert(
    monkeypatch: pytest.MonkeyPatch,
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Advance the transaction watermark only after records are persisted."""
    events: list[str] = []
    original_upsert_many = database.upsert_many
    original_upsert_metadata = database.upsert_sync_metadata

    async def tracked_upsert_many(records: Any) -> Any:
        """Record completion of the data upsert."""
        result = await original_upsert_many(records)
        events.append("records")
        return result

    async def tracked_upsert_metadata(metadata: SyncMetadata) -> SyncMetadata:
        """Record the watermark write after persisting it."""
        result = await original_upsert_metadata(metadata)
        events.append("watermark")
        return result

    monkeypatch.setattr(database, "upsert_many", tracked_upsert_many)
    monkeypatch.setattr(database, "upsert_sync_metadata", tracked_upsert_metadata)
    started_at = datetime.datetime.now(datetime.timezone.utc)

    await sync_database(
        db=database,
        client=cast(LunchMoneyApp, client),
        incremental=True,
    )

    stored = await database.get_sync_metadata("transactions")
    assert stored is not None
    assert (
        started_at
        <= stored.last_synced_at
        <= datetime.datetime.now(datetime.timezone.utc)
    )
    assert events[0] == "records"
    assert "watermark" in events[1:]


@pytest.mark.asyncio
async def test_failed_incremental_sync_does_not_advance_watermark(
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Preserve an existing watermark when the transaction refresh fails."""
    watermark = datetime.datetime(2026, 7, 28, 12, 0, tzinfo=datetime.timezone.utc)
    await database.upsert_sync_metadata(
        SyncMetadata(domain="transactions", last_synced_at=watermark)
    )
    client.refresh_transactions.side_effect = RuntimeError("synthetic upstream failure")

    with pytest.raises(RuntimeError, match="synthetic upstream failure"):
        await sync_database(
            db=database,
            client=cast(LunchMoneyApp, client),
            incremental=True,
        )

    stored = await database.get_sync_metadata("transactions")
    assert stored is not None
    assert stored.last_synced_at == watermark


@pytest.mark.asyncio
async def test_failed_incremental_upsert_does_not_advance_watermark(
    monkeypatch: pytest.MonkeyPatch,
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Leave the watermark absent when persistence of refreshed data fails."""
    monkeypatch.setattr(
        database,
        "upsert_many",
        AsyncMock(side_effect=RuntimeError("synthetic database failure")),
    )

    with pytest.raises(RuntimeError, match="synthetic database failure"):
        await sync_database(
            db=database,
            client=cast(LunchMoneyApp, client),
            incremental=True,
        )

    assert await database.get_sync_metadata("transactions") is None


@pytest.mark.asyncio
async def test_non_incremental_sync_preserves_date_window_without_watermark(
    database: LunchMoneyDatabase,
    client: AsyncMock,
) -> None:
    """Keep the existing date-window query and avoid watermark writes by default."""
    start_date = datetime.date(2026, 6, 1)
    end_date = datetime.date(2026, 7, 1)

    await sync_database(
        db=database,
        client=cast(LunchMoneyApp, client),
        start_date=start_date,
        end_date=end_date,
    )

    client.refresh_transactions.assert_awaited_once_with(
        start_date=start_date,
        end_date=end_date,
        cache=False,
    )
    assert (await database.get_sync_metadata("transactions")) is not None
