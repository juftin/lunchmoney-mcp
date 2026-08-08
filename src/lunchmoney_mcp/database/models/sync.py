"""SQLModel record for incremental synchronization watermarks."""

from builtins import type as builtin_type
from datetime import datetime, timezone
from typing import Any, ClassVar, cast

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel
from lunchmoney_mcp.database.models._datetime import UTCDateTime


UTC = timezone.utc
"""Canonical UTC timezone compatible with all supported Python versions."""


class SyncMetadata(SQLModel, table=True):
    """Persist the latest successful synchronization time for one domain."""

    __tablename__: ClassVar[str] = "sync_metadata"

    domain: str = Field(primary_key=True)
    """Synchronization domain uniquely identified by this watermark."""
    last_synced_at: datetime = Field(sa_type=cast(builtin_type[Any], UTCDateTime()))
    """UTC timestamp of the domain's latest successful synchronization."""
    payload: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    """Optional domain metadata payload persisted during synchronization."""

    def model_post_init(self, context: Any, /) -> None:
        """Normalize synchronization watermarks after SQLModel construction."""
        del context
        if self.last_synced_at.tzinfo is None:
            self.last_synced_at = self.last_synced_at.replace(tzinfo=UTC)
        else:
            self.last_synced_at = self.last_synced_at.astimezone(UTC)


class ScheduledSyncRun(SQLModel, table=True):
    """Persist the final status and record counts from one scheduled sync run."""

    __tablename__: ClassVar[str] = "scheduled_sync_runs"

    id: int | None = Field(default=None, primary_key=True)
    """Database-generated identifier for the completed scheduler run."""
    status: str
    """Final scheduler run state: success, failed, or skipped."""
    started_at: datetime = Field(
        sa_type=cast(builtin_type[Any], UTCDateTime()),
        index=True,
    )
    """UTC timestamp at which the scheduler attempted the sync."""
    finished_at: datetime = Field(sa_type=cast(builtin_type[Any], UTCDateTime()))
    """UTC timestamp at which the scheduler recorded its final result."""
    message: str | None = None
    """Safe operator-facing explanation for failures or skipped runs."""
    synced: dict[str, int] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    """Record counts returned by a successful synchronization, when available."""

    def model_post_init(self, context: Any, /) -> None:
        """Normalize run timestamps to UTC after SQLModel construction."""
        del context
        for attribute in ("started_at", "finished_at"):
            timestamp = getattr(self, attribute)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            else:
                timestamp = timestamp.astimezone(UTC)
            setattr(self, attribute, timestamp)
