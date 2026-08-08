"""Dedicated APScheduler 3 runtime for periodic Lunch Money synchronization."""

import asyncio
import logging
import os
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from lunchmoney_mcp.app.dependencies import get_database, get_lunchmoney_app
from lunchmoney_mcp.config import RuntimeSettings, get_settings
from lunchmoney_mcp.services import run_scheduled_sync as execute_scheduled_sync

logger = logging.getLogger(__name__)

SCHEDULE_ID: str = "lunchmoney-scheduled-sync"
"""Stable APScheduler identifier for the recurring synchronization schedule."""
SCHEDULE_TRANSACTIONS_ID: str = "lunchmoney-scheduled-sync-transactions"
"""Stable APScheduler identifier for transaction database synchronization."""
SCHEDULE_METADATA_ID: str = "lunchmoney-scheduled-sync-metadata"
"""Stable APScheduler identifier for metadata database synchronization."""

_active_sync_tasks: set[asyncio.Task[None]] = set()
"""In-process scheduled sync tasks awaited during orderly scheduler shutdown."""


class SchedulerConfigurationError(ValueError):
    """Raised when a scheduler cron expression or timezone is invalid."""


class EmbeddedSchedulerConfigurationError(SchedulerConfigurationError):
    """Raised when embedded scheduling is enabled outside local single-process use."""


def build_scheduler(
    settings: RuntimeSettings,
    timezone: str | None = None,
) -> AsyncIOScheduler:
    """Create the single-process scheduler with safe job defaults.

    Parameters
    ----------
    settings : RuntimeSettings
        Application configuration controlling the scheduler.
    timezone : str | None
        Optional timezone override for this scheduler process.

    Returns
    -------
    AsyncIOScheduler
        An unstarted stable APScheduler 3 scheduler.
    """
    return AsyncIOScheduler(
        timezone=timezone or settings.schedule_timezone,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": None,
        },
    )


async def run_schedule_process(
    settings: RuntimeSettings | None = None,
    cron: str | None = None,
    timezone: str | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Start the dedicated scheduler and run until it receives shutdown.

    Parameters
    ----------
    settings : RuntimeSettings | None
        Explicit settings for testing or embedded use. Defaults to environment settings.
    cron : str | None
        Optional five-field cron override for this scheduler process.
    timezone : str | None
        Optional IANA timezone override for the cron expression.
    shutdown_event : asyncio.Event | None
        Optional event used by embedded callers to request orderly shutdown.

    Raises
    ------
    SchedulerConfigurationError
        If the cron expression or timezone is invalid.
    """
    resolved_settings = settings or get_settings()
    cron_expression = cron or resolved_settings.schedule_cron
    resolved_timezone = timezone or resolved_settings.schedule_timezone
    scheduler = _create_scheduler(
        settings=resolved_settings,
        cron=cron_expression,
        timezone=resolved_timezone,
    )
    resolved_shutdown_event = shutdown_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    handled_signals = (signal.SIGINT, signal.SIGTERM)
    installed_signals: list[signal.Signals] = []
    for shutdown_signal in handled_signals:
        try:
            loop.add_signal_handler(
                shutdown_signal,
                resolved_shutdown_event.set,
            )
        except NotImplementedError:
            logger.debug("Signal handlers are unavailable in this scheduler runtime")
        else:
            installed_signals.append(shutdown_signal)

    try:
        scheduler.start()
        logger.info(
            "Starting scheduled synchronization with cron %s in %s",
            cron_expression,
            resolved_timezone,
        )
        await resolved_shutdown_event.wait()
    finally:
        await stop_scheduler(scheduler)
        for shutdown_signal in installed_signals:
            loop.remove_signal_handler(shutdown_signal)


def start_embedded_scheduler(
    settings: RuntimeSettings | None = None,
) -> AsyncIOScheduler:
    """Start a scheduler inside one local FastAPI process.

    Parameters
    ----------
    settings : RuntimeSettings | None
        Explicit settings for testing or embedded use. Defaults to environment settings.

    Returns
    -------
    AsyncIOScheduler
        Running local scheduler owned by the FastAPI lifespan.

    Raises
    ------
    EmbeddedSchedulerConfigurationError
        If the process is Gunicorn, has multiple configured workers, or is not local.
    """
    resolved_settings = settings or get_settings()
    _validate_embedded_scheduler_settings(resolved_settings)
    scheduler = _create_scheduler(
        settings=resolved_settings,
        cron=resolved_settings.schedule_cron,
        timezone=resolved_settings.schedule_timezone,
    )
    scheduler.start()
    logger.info("Started local scheduler inside FastAPI lifespan")
    return scheduler


async def stop_scheduler(scheduler: AsyncIOScheduler) -> None:
    """Pause a scheduler and let in-flight scheduled synchronization finish."""
    if not scheduler.running:
        return
    scheduler.pause()
    await _wait_for_active_syncs()
    scheduler.shutdown(wait=False)


def _normalize_cron(raw: str | None) -> str | None:
    """Normalize cron string and return None if disabled or empty."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if cleaned in {"", "none", "disabled", "false", "0", "null", "off"}:
        return None
    return raw.strip()


def _create_scheduler(
    settings: RuntimeSettings,
    cron: str | None = None,
    timezone: str | None = None,
) -> AsyncIOScheduler:
    """Create a scheduler and register its stable, coalescing synchronization jobs."""
    resolved_timezone = timezone or settings.schedule_timezone
    txn_cron_str = _normalize_cron(
        cron or settings.schedule_transactions_cron or settings.schedule_cron
    )
    meta_cron_str = _normalize_cron(settings.schedule_metadata_cron)

    if cron is not None or settings.embed_scheduler:
        if txn_cron_str is None:
            txn_cron_str = "*/10 * * * *"
        if meta_cron_str is None:
            meta_cron_str = "0 * * * *"

    scheduler = build_scheduler(settings, timezone=resolved_timezone)
    if txn_cron_str is not None:
        try:
            txn_trigger = CronTrigger.from_crontab(
                txn_cron_str, timezone=resolved_timezone
            )
            scheduler.add_job(
                run_scheduled_sync,
                trigger=txn_trigger,
                id=SCHEDULE_TRANSACTIONS_ID,
                coalesce=True,
                max_instances=1,
                replace_existing=True,
            )
        except (TypeError, ValueError) as error:
            msg = f"Invalid scheduler cron or timezone: {error}"
            raise SchedulerConfigurationError(msg) from error

    if meta_cron_str is not None:
        try:
            meta_trigger = CronTrigger.from_crontab(
                meta_cron_str, timezone=resolved_timezone
            )
            scheduler.add_job(
                run_scheduled_sync,
                trigger=meta_trigger,
                id=SCHEDULE_METADATA_ID,
                coalesce=True,
                max_instances=1,
                replace_existing=True,
            )
        except (TypeError, ValueError) as error:
            msg = f"Invalid scheduler cron or timezone: {error}"
            raise SchedulerConfigurationError(msg) from error

    return scheduler


def _validate_embedded_scheduler_settings(settings: RuntimeSettings) -> None:
    """Reject embedded scheduler startup outside local single-process development."""
    if settings.environment != "development":
        msg = "Embedded scheduling requires LUNCHMONEY_ENVIRONMENT=development."
        raise EmbeddedSchedulerConfigurationError(msg)
    if _is_gunicorn_process():
        msg = "Embedded scheduling cannot run in a Gunicorn process."
        raise EmbeddedSchedulerConfigurationError(msg)
    if _configured_worker_count() > 1:
        msg = "Embedded scheduling requires exactly one configured web worker."
        raise EmbeddedSchedulerConfigurationError(msg)


def _is_gunicorn_process() -> bool:
    """Return whether the current process was launched by Gunicorn."""
    return any("gunicorn" in argument.lower() for argument in sys.argv)


def _configured_worker_count() -> int:
    """Read explicit web-worker configuration from environment or command arguments."""
    if configured_workers := os.getenv("WEB_CONCURRENCY"):
        return int(configured_workers)
    for index, argument in enumerate(sys.argv):
        if argument.startswith("--workers="):
            return int(argument.split("=", maxsplit=1)[1])
        if argument == "--workers" and index + 1 < len(sys.argv):
            return int(sys.argv[index + 1])
    return 1


async def run_scheduled_sync() -> None:
    """Execute the configured scheduled sync using process-local dependencies."""
    task = asyncio.current_task()
    if task is not None:
        _active_sync_tasks.add(task)
    try:
        settings = get_settings()
        result = await execute_scheduled_sync(
            db=get_database(),
            client=get_lunchmoney_app(),
            days=settings.schedule_days,
        )
        log_method = logger.info if result.status == "success" else logger.warning
        log_method(
            "Scheduled synchronization %s; started=%s finished=%s",
            result.status,
            result.started_at.isoformat(),
            result.finished_at.isoformat(),
        )
    finally:
        if task is not None:
            _active_sync_tasks.discard(task)


async def _wait_for_active_syncs() -> None:
    """Wait for any running scheduler task before shutting down its executor."""
    while _active_sync_tasks:
        await asyncio.gather(*_active_sync_tasks, return_exceptions=True)


__all__ = [
    "SCHEDULE_ID",
    "EmbeddedSchedulerConfigurationError",
    "SchedulerConfigurationError",
    "build_scheduler",
    "run_schedule_process",
    "run_scheduled_sync",
    "start_embedded_scheduler",
    "stop_scheduler",
]
