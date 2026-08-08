"""Tests for scheduled synchronization runtime and operator status reporting."""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lunchmoney_mcp.config import RuntimeSettings
from lunchmoney_mcp.schemas import ScheduledSyncStatus, SyncDetails, SyncResponse


class _SchedulerDouble:
    """Minimal APScheduler 3 double that supports lifecycle assertions."""

    def __init__(self) -> None:
        """Create scheduler methods and a running state for lifecycle assertions."""
        self.add_job = Mock()
        self.start = Mock()
        self.pause = Mock()
        self.shutdown = Mock()
        self.running = True


class _ContendedLock:
    """Lock double that models another worker already synchronizing."""

    def acquire(self, blocking: bool = True, timeout: float | int = -1) -> bool:
        """Reject acquisition attempts to simulate duplicate work prevention."""
        del blocking, timeout
        return False

    def release(self) -> None:
        """Provide the lock interface method that is never reached in this double."""


class _AcquiredLock:
    """Lock double that tracks one successful synchronization acquisition."""

    def __init__(self) -> None:
        """Create a release marker for assertions."""
        self.released = False

    def acquire(self, blocking: bool = True, timeout: float | int = -1) -> bool:
        """Acquire the test lock immediately."""
        del blocking, timeout
        return True

    def release(self) -> None:
        """Record lock release after the scheduled synchronization finishes."""
        self.released = True


def test_scheduler_uses_stable_single_process_runtime() -> None:
    """Use APScheduler 3's asyncio runtime with coalesced single-instance jobs."""
    from lunchmoney_mcp.scheduler import build_scheduler

    scheduler = build_scheduler(RuntimeSettings())

    assert isinstance(scheduler, AsyncIOScheduler)
    assert scheduler._job_defaults == {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": None,
    }


def test_embedded_scheduler_starts_inside_local_fastapi_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Start the same scheduler from an explicit local FastAPI lifespan mode."""
    import lunchmoney_mcp.scheduler as scheduler_module

    scheduler = _SchedulerDouble()
    monkeypatch.setattr(
        scheduler_module,
        "build_scheduler",
        lambda settings, timezone: scheduler,
    )

    started = scheduler_module.start_embedded_scheduler(settings=RuntimeSettings())

    assert started is scheduler
    assert scheduler.add_job.call_count == 2
    scheduler.start.assert_called_once()


@pytest.mark.parametrize(
    ("arguments", "web_concurrency", "environment", "message"),
    [
        (["gunicorn"], None, "development", "Gunicorn"),
        (["uvicorn"], "2", "development", "exactly one"),
        (["uvicorn"], None, "production", "LUNCHMONEY_ENVIRONMENT=development"),
    ],
)
def test_embedded_scheduler_rejects_nonlocal_or_multiworker_runtime(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
    web_concurrency: str | None,
    environment: str,
    message: str,
) -> None:
    """Reject embedded scheduling in deployment modes that could duplicate jobs."""
    import lunchmoney_mcp.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module.sys, "argv", arguments)
    if web_concurrency is None:
        monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("WEB_CONCURRENCY", web_concurrency)

    with pytest.raises(
        scheduler_module.EmbeddedSchedulerConfigurationError,
        match=message,
    ):
        scheduler_module.start_embedded_scheduler(
            settings=RuntimeSettings(environment=environment)
        )


@pytest.mark.asyncio
async def test_schedule_process_coalesces_and_replaces_its_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Register coalesced jobs for transactions and metadata workloads and close gracefully."""
    import lunchmoney_mcp.scheduler as scheduler_module

    scheduler = _SchedulerDouble()
    monkeypatch.setattr(
        scheduler_module,
        "build_scheduler",
        lambda settings, timezone: scheduler,
    )
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await scheduler_module.run_schedule_process(
        settings=RuntimeSettings(),
        shutdown_event=shutdown_event,
    )

    assert scheduler.add_job.call_count == 2
    calls = scheduler.add_job.call_args_list
    assert calls[0].kwargs["id"] == scheduler_module.SCHEDULE_TRANSACTIONS_ID
    assert calls[1].kwargs["id"] == scheduler_module.SCHEDULE_METADATA_ID
    assert calls[0].kwargs["coalesce"] is True
    assert calls[0].kwargs["max_instances"] == 1
    assert calls[0].kwargs["replace_existing"] is True
    scheduler.start.assert_called_once()
    scheduler.pause.assert_called_once()
    scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_scheduled_sync_skips_when_another_run_holds_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist a skipped result instead of starting duplicate concurrent work."""
    import lunchmoney_mcp.services.sync as sync_service

    database = MagicMock()
    database.record_scheduled_sync_run = AsyncMock()
    execute_sync = AsyncMock()
    monkeypatch.setattr(sync_service, "get_migration_lock", _ContendedLock)
    monkeypatch.setattr(sync_service, "execute_sync", execute_sync)

    result = await sync_service.run_scheduled_sync(
        db=database,
        client=MagicMock(),
    )

    assert result.status == "skipped"
    execute_sync.assert_not_awaited()
    database.record_scheduled_sync_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_sync_records_incremental_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use incremental sync and persist its successful record-count summary."""
    import lunchmoney_mcp.services.sync as sync_service

    lock = _AcquiredLock()
    database = MagicMock()
    database.record_scheduled_sync_run = AsyncMock()
    response = SyncResponse(
        synced=SyncDetails(
            user=1,
            plaid_accounts=2,
            manual_accounts=3,
            categories=4,
            tags=5,
            transactions=6,
            total=21,
        )
    )
    execute_sync = AsyncMock(return_value=response)
    monkeypatch.setattr(sync_service, "get_migration_lock", lambda: lock)
    monkeypatch.setattr(sync_service, "execute_sync", execute_sync)

    client = MagicMock()
    result = await sync_service.run_scheduled_sync(
        db=database,
        client=client,
        days=45,
    )

    assert result.status == "success"
    assert result.synced == response.synced
    execute_sync.assert_awaited_once_with(
        db=database,
        client=client,
        days=45,
        incremental=True,
    )
    assert lock.released is True
    recorded_call = database.record_scheduled_sync_run.await_args
    assert recorded_call is not None
    recorded = recorded_call.args[0]
    assert recorded.status == "success"
    assert recorded.synced == response.synced.model_dump(mode="json")


@pytest.mark.asyncio
async def test_scheduled_sync_status_maps_persisted_record() -> None:
    """Expose the last persisted scheduler result in the public response schema."""
    from lunchmoney_mcp.database import ScheduledSyncRun
    from lunchmoney_mcp.services.sync import get_scheduled_sync_status

    timestamp = datetime.datetime(2026, 7, 30, tzinfo=datetime.timezone.utc)
    database = MagicMock()
    database.get_latest_scheduled_sync_run = AsyncMock(
        return_value=ScheduledSyncRun(
            id=1,
            status="success",
            started_at=timestamp,
            finished_at=timestamp,
            synced={
                "user": 1,
                "plaid_accounts": 0,
                "manual_accounts": 0,
                "categories": 0,
                "tags": 0,
                "transactions": 0,
                "total": 1,
            },
        )
    )

    status = await get_scheduled_sync_status(database)

    assert status == ScheduledSyncStatus(
        status="success",
        started_at=timestamp,
        finished_at=timestamp,
        synced=SyncDetails(
            user=1,
            plaid_accounts=0,
            manual_accounts=0,
            categories=0,
            tags=0,
            transactions=0,
            total=1,
        ),
    )
