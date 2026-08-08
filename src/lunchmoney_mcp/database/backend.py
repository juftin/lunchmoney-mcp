"""Async SQLModel database configuration and lifecycle helpers."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from heapq import heappop, heappush
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar, cast

from typing_extensions import Self

from alembic import command
from alembic.config import Config

from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import QueryableAttribute, selectinload
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from lunchmoney_mcp.config import (
    DEFAULT_DATABASE_URL,
    IN_MEMORY_DATABASE_URL,
    SecretSettings,
    get_settings,
    get_runtime_mode,
)
from lunchmoney_mcp.database.models import (
    Category,
    ManualAccount,
    PlaidAccount,
    ScheduledSyncRun,
    SyncMetadata,
    Tag,
    Transaction,
    TransactionAttachment,
    TransactionKind,
    TransactionTagLink,
    User,
)


RecordT = TypeVar("RecordT", bound=SQLModel)
"""A database record subtype used by record-loading helpers."""

_SUPPORTED_MODELS: frozenset[type[SQLModel]] = frozenset(
    {User, PlaidAccount, ManualAccount, Category, Tag, Transaction}
)
"""Explicit record classes accepted by the convenience persistence API."""


PROJECT_ROOT: Path = Path(__file__).parents[3]
"""Repository root containing the Alembic configuration."""

__all__ = [
    "DEFAULT_DATABASE_URL",
    "IN_MEMORY_DATABASE_URL",
    "LunchMoneyDatabase",
    "resolve_database_url",
    "run_migrations",
]


def resolve_database_url(database_url: str | None = None) -> str:
    """Resolve an explicit, environment-provided, or default database URL."""
    if database_url is not None:
        return database_url
    if get_runtime_mode() == "mcp":
        return IN_MEMORY_DATABASE_URL
    env_url = os.getenv("LUNCHMONEY_DATABASE_URL")
    if env_url:
        return env_url
    secret_settings = SecretSettings()
    if "database_url" in secret_settings.model_fields_set:
        return secret_settings.database_url
    if get_settings().stateless:
        return IN_MEMORY_DATABASE_URL
    return DEFAULT_DATABASE_URL


async def run_migrations(
    database_url: str | None = None, revision: str = "head"
) -> None:
    """Run Alembic database migrations to upgrade the schema."""

    def _sync_upgrade() -> None:
        resolved_url = resolve_database_url(database_url)
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", resolved_url.replace("%", "%%"))
        command.upgrade(config, revision)

    await asyncio.to_thread(_sync_upgrade)


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    """Enable SQLite foreign-key enforcement on one newly opened connection."""
    del connection_record
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _ensure_supported_model(model: type[SQLModel]) -> None:
    """Reject model classes outside the explicitly supported public records."""
    if model not in _SUPPORTED_MODELS:
        msg = f"Unsupported SQLModel model: {model.__name__}"
        raise TypeError(msg)


def _ensure_supported_record(record: SQLModel) -> None:
    """Reject record instances outside the explicitly supported public records."""
    if type(record) not in _SUPPORTED_MODELS:
        msg = f"Unsupported SQLModel record: {type(record).__name__}"
        raise TypeError(msg)


def _model_rank(record: SQLModel) -> int:
    """Return the broad persistence rank for one supported record."""
    record_type = type(record)
    if record_type is User:
        return 0
    if record_type in {PlaidAccount, ManualAccount}:
        return 1
    if record_type is Category:
        return 2
    if record_type is Tag:
        return 3
    if record_type is Transaction:
        return 4
    msg = f"Unsupported SQLModel record: {record_type.__name__}"
    raise TypeError(msg)


def _dependency_order(records: list[SQLModel]) -> list[tuple[int, SQLModel]]:
    """Return a stable broad-rank and self-foreign-key topological ordering."""
    identity_indices: dict[tuple[type[SQLModel], int], int] = {}
    for index, record in enumerate(records):
        identity = (type(record), _record_primary_key(record))
        identity_indices.setdefault(identity, index)

    dependencies: dict[int, set[int]] = {index: set() for index in range(len(records))}
    dependents: dict[int, set[int]] = {index: set() for index in range(len(records))}
    for index, record in enumerate(records):
        parent_identities: list[tuple[type[SQLModel], int]] = []
        if type(record) is Category:
            category = record
            if category.group_id is not None:
                parent_identities.append((Category, category.group_id))
        elif type(record) is Transaction:
            transaction = record
            for parent_id in (
                transaction.split_parent_id,
                transaction.group_parent_id,
            ):
                if parent_id is not None:
                    parent_identities.append((Transaction, parent_id))

        for parent_identity in parent_identities:
            parent_index = identity_indices.get(parent_identity)
            if parent_index is None or parent_index == index:
                continue
            dependencies[index].add(parent_index)
            dependents[parent_index].add(index)

    ordered: list[tuple[int, SQLModel]] = []
    for rank in range(5):
        rank_indices = [
            index for index, record in enumerate(records) if _model_rank(record) == rank
        ]
        ready: list[int] = []
        for index in rank_indices:
            if not dependencies[index]:
                heappush(ready, index)

        ordered_indices: set[int] = set()
        while ready:
            index = heappop(ready)
            ordered_indices.add(index)
            ordered.append((index, records[index]))
            for dependent_index in sorted(dependents[index]):
                dependencies[dependent_index].discard(index)
                if not dependencies[dependent_index]:
                    heappush(ready, dependent_index)

        for index in rank_indices:
            if index not in ordered_indices:
                ordered.append((index, records[index]))
    return ordered


def _record_primary_key(record: SQLModel) -> int:
    """Return the integer primary key of an explicitly supported record."""
    record_type = type(record)
    if record_type is User:
        return cast(User, record).id
    if record_type is PlaidAccount:
        return cast(PlaidAccount, record).id
    if record_type is ManualAccount:
        return cast(ManualAccount, record).id
    if record_type is Category:
        return cast(Category, record).id
    if record_type is Tag:
        return cast(Tag, record).id
    if record_type is Transaction:
        return cast(Transaction, record).id
    msg = f"Unsupported SQLModel record: {record_type.__name__}"
    raise TypeError(msg)


def _primary_key_attribute(model: type[SQLModel]) -> Any:
    """Return the mapped identifier attribute for a supported model class."""
    if model is User:
        return User.id
    if model is PlaidAccount:
        return PlaidAccount.id
    if model is ManualAccount:
        return ManualAccount.id
    if model is Category:
        return Category.id
    if model is Tag:
        return Tag.id
    if model is Transaction:
        return Transaction.id
    msg = f"Unsupported SQLModel model: {model.__name__}"
    raise TypeError(msg)


def _loader_attribute(value: Any) -> QueryableAttribute[Any]:
    """Narrow a SQLModel relationship annotation to its mapped class attribute."""
    return cast(QueryableAttribute[Any], value)


def eager_options(model: type[SQLModel]) -> tuple[Any, ...]:
    """Return explicit eager-loading rules for one supported record class."""
    if model is Category:
        parent = _loader_attribute(Category.parent)
        children = _loader_attribute(Category.children)
        return (
            selectinload(parent),
            selectinload(children),
            selectinload(parent).selectinload(children),
            selectinload(children).selectinload(parent),
        )
    if model is Transaction:
        category = _loader_attribute(Transaction.category)
        category_children = _loader_attribute(Category.children)
        plaid_account = _loader_attribute(Transaction.plaid_account)
        manual_account = _loader_attribute(Transaction.manual_account)
        split_parent = _loader_attribute(Transaction.split_parent)
        group_parent = _loader_attribute(Transaction.group_parent)
        tag_links = _loader_attribute(Transaction.tag_links)
        link_tag = _loader_attribute(TransactionTagLink.tag)
        tags = _loader_attribute(Transaction.tags)
        attachments = _loader_attribute(Transaction.attachments)
        split_children = _loader_attribute(Transaction.split_children)
        group_children = _loader_attribute(Transaction.group_children)
        return (
            selectinload(category).selectinload(category_children),
            selectinload(plaid_account),
            selectinload(manual_account),
            selectinload(split_parent),
            selectinload(group_parent),
            selectinload(tag_links).selectinload(link_tag),
            selectinload(tags),
            selectinload(attachments),
            selectinload(split_children)
            .selectinload(category)
            .selectinload(category_children),
            selectinload(split_children).selectinload(plaid_account),
            selectinload(split_children).selectinload(manual_account),
            selectinload(split_children).selectinload(tag_links).selectinload(link_tag),
            selectinload(split_children).selectinload(tags),
            selectinload(split_children).selectinload(attachments),
            selectinload(split_children).selectinload(split_parent),
            selectinload(split_children).selectinload(group_parent),
            selectinload(group_children)
            .selectinload(category)
            .selectinload(category_children),
            selectinload(group_children).selectinload(plaid_account),
            selectinload(group_children).selectinload(manual_account),
            selectinload(group_children).selectinload(tag_links).selectinload(link_tag),
            selectinload(group_children).selectinload(tags),
            selectinload(group_children).selectinload(attachments),
            selectinload(group_children).selectinload(split_parent),
            selectinload(group_children).selectinload(group_parent),
        )
    return ()


_eager_options = eager_options


def _clone_category_record(record: Category) -> Category:
    """Copy one transient category row without carrying ORM session state."""
    clone = Category.model_validate(record.model_dump())
    clone.children = []
    return clone


def _clone_transaction_record(record: Transaction) -> Transaction:
    """Copy one transient transaction row and normalize metadata presence."""
    clone = Transaction.model_validate(record.model_dump())
    clone.plaid_metadata_present = (
        record.plaid_metadata_present or record.plaid_metadata is not None
    )
    clone.custom_metadata_present = (
        record.custom_metadata_present or record.custom_metadata is not None
    )
    clone.tag_links = []
    clone.attachments = []
    clone.split_children = []
    clone.group_children = []
    return clone


def _clone_transaction_graph(record: Transaction) -> Transaction:
    """Copy a transaction graph without shared records or ORM session state."""
    clone = _clone_transaction_record(record)
    clone.tag_links = [
        TransactionTagLink.model_validate(link.model_dump())
        for link in record.tag_links
    ]
    clone.attachments = [
        TransactionAttachment.model_validate(attachment.model_dump())
        for attachment in record.attachments
    ]
    clone.split_children = [
        _clone_transaction_graph(child) for child in record.split_children
    ]
    clone.group_children = [
        _clone_transaction_graph(child) for child in record.group_children
    ]
    return clone


def _replacement_attachments(
    existing: Transaction,
    incoming: Transaction,
) -> list[TransactionAttachment]:
    """Reconcile attachment identity while replacing an owned collection."""
    by_id = {
        attachment.id: attachment
        for attachment in existing.attachments
        if attachment.id is not None
    }
    by_api_id = {
        attachment.api_id: attachment
        for attachment in existing.attachments
        if attachment.api_id is not None
    }
    used: set[int] = set()
    replacement: list[TransactionAttachment] = []
    for position, attachment in enumerate(incoming.attachments):
        managed = by_id.get(attachment.id) if attachment.id is not None else None
        if managed is None and attachment.api_id is not None:
            managed = by_api_id.get(attachment.api_id)
        if managed is not None and id(managed) not in used:
            managed.sqlmodel_update(attachment.model_dump(exclude={"id"}))
            managed.transaction_id = existing.id
            managed.position = position
            used.add(id(managed))
            replacement.append(managed)
            continue
        clone = TransactionAttachment.model_validate(attachment.model_dump())
        clone.transaction_id = existing.id
        clone.position = position
        replacement.append(clone)
    return replacement


def _replacement_tag_links(
    existing: Transaction,
    incoming: Transaction,
) -> list[TransactionTagLink]:
    """Reconcile composite link identity while replacing tag associations."""
    by_tag_id = {link.tag_id: link for link in existing.tag_links}
    replacement: list[TransactionTagLink] = []
    for link in incoming.tag_links:
        managed = by_tag_id.get(link.tag_id)
        if managed is not None:
            managed.position = link.position
            replacement.append(managed)
            continue
        replacement.append(
            TransactionTagLink(
                transaction_id=existing.id,
                tag_id=link.tag_id,
                position=link.position,
            )
        )
    return replacement


async def _update_category_graph(
    session: AsyncSession,
    existing: Category,
    incoming: Category,
) -> None:
    """Update category scalars and replace explicitly supplied children."""
    values = incoming.model_dump()
    if not incoming.children_present:
        values.pop("children_present")
    existing.sqlmodel_update(values)
    if not incoming.children_present:
        return

    by_id = {child.id: child for child in existing.children}
    replacement: list[Category] = []
    for child in incoming.children:
        managed = by_id.get(child.id)
        if managed is None:
            managed = await _load_record(session, Category, child.id)
        if managed is not None:
            managed.sqlmodel_update(child)
            managed.group_id = existing.id
            replacement.append(managed)
            continue
        clone = _clone_category_record(child)
        clone.group_id = existing.id
        replacement.append(clone)
    existing.children = replacement


def _transaction_update_values(incoming: Transaction) -> dict[str, Any]:
    """Return scalar update values honoring optional metadata masks."""
    values = incoming.model_dump()
    plaid_metadata_present = (
        incoming.plaid_metadata_present or incoming.plaid_metadata is not None
    )
    custom_metadata_present = (
        incoming.custom_metadata_present or incoming.custom_metadata is not None
    )
    values["plaid_metadata_present"] = plaid_metadata_present
    values["custom_metadata_present"] = custom_metadata_present
    if not incoming.children_present and (
        TransactionKind(incoming.kind) is not TransactionKind.CHILD
    ):
        values.pop("children_present")
    if not incoming.files_present:
        values.pop("files_present")
    if not plaid_metadata_present:
        values.pop("plaid_metadata")
        values.pop("plaid_metadata_present")
    if not custom_metadata_present:
        values.pop("custom_metadata")
        values.pop("custom_metadata_present")
    return values


async def _update_transaction_graph(
    session: AsyncSession,
    existing: Transaction,
    incoming: Transaction,
) -> None:
    """Update transaction scalars and replace explicitly supplied collections."""
    is_child = TransactionKind(incoming.kind) is TransactionKind.CHILD
    if is_child:
        await session.refresh(
            existing,
            attribute_names=["split_children", "group_children"],
        )
    existing.sqlmodel_update(_transaction_update_values(incoming))
    if incoming.files_present:
        existing.attachments = _replacement_attachments(existing, incoming)
    existing.tag_links = _replacement_tag_links(existing, incoming)

    if is_child:
        existing.split_children = []
        existing.group_children = []
        return

    if not incoming.children_present:
        return

    managed_children = {
        child.id: child
        for child in [*existing.split_children, *existing.group_children]
    }

    split_replacement: list[Transaction] = []
    for child in incoming.split_children:
        managed = managed_children.get(child.id)
        if managed is None:
            managed = await _load_record(session, Transaction, child.id)
        if managed is not None:
            await _update_transaction_graph(session, managed, child)
        else:
            managed = _clone_transaction_graph(child)
        managed.split_parent_id = existing.id
        managed.group_parent_id = None
        split_replacement.append(managed)

    group_replacement: list[Transaction] = []
    for child in incoming.group_children:
        managed = managed_children.get(child.id)
        if managed is None:
            managed = await _load_record(session, Transaction, child.id)
        if managed is not None:
            await _update_transaction_graph(session, managed, child)
        else:
            managed = _clone_transaction_graph(child)
        managed.split_parent_id = None
        managed.group_parent_id = existing.id
        group_replacement.append(managed)

    existing.split_children = split_replacement
    existing.group_children = group_replacement


async def _detach_claimed_children(
    session: AsyncSession,
    records: Iterable[SQLModel],
) -> None:
    """Detach existing claimed children before caller-ordered graph additions."""
    category_child_ids: set[int] = set()
    transaction_child_ids: set[int] = set()
    for record in records:
        if type(record) is Category:
            category = record
            if category.children_present:
                category_child_ids.update(child.id for child in category.children)
        elif type(record) is Transaction:
            transaction = record
            if transaction.children_present:
                transaction_child_ids.update(
                    child.id
                    for child in [
                        *transaction.split_children,
                        *transaction.group_children,
                    ]
                )

    if category_child_ids:
        await session.exec(
            update(Category)
            .where(_primary_key_attribute(Category).in_(category_child_ids))
            .values(group_id=None)
        )
    if transaction_child_ids:
        await session.exec(
            update(Transaction)
            .where(_primary_key_attribute(Transaction).in_(transaction_child_ids))
            .values(split_parent_id=None, group_parent_id=None)
        )


async def _load_record(
    session: AsyncSession,
    model: type[RecordT],
    primary_key: int,
) -> RecordT | None:
    """Load one supported record with its explicit detached-record graph."""
    supported_model = cast(type[SQLModel], model)
    statement = (
        select(model)
        .where(_primary_key_attribute(supported_model) == primary_key)
        .options(*_eager_options(supported_model))
    )
    result = await session.exec(statement)
    return result.one_or_none()


async def _upsert_record(session: AsyncSession, record: SQLModel) -> None:
    """Insert or update one supported record without committing its session."""
    record_type = type(record)
    primary_key = _record_primary_key(record)
    if record_type is Category:
        category = cast(Category, record)
        existing_category = await _load_record(session, Category, primary_key)
        if existing_category is None:
            existing_category = _clone_category_record(category)
            session.add(existing_category)
            await session.flush()
        await _update_category_graph(session, existing_category, category)
        return
    if record_type is Transaction:
        transaction = cast(Transaction, record)
        existing_transaction = await _load_record(session, Transaction, primary_key)
        if existing_transaction is None:
            existing_transaction = _clone_transaction_record(transaction)
            session.add(existing_transaction)
            await session.flush()
        await _update_transaction_graph(session, existing_transaction, transaction)
        return

    existing = await session.get(record_type, primary_key)
    if existing is None:
        session.add(record)
    else:
        existing.sqlmodel_update(record)


class LunchMoneyDatabase:
    """Own the application's async database engine and session factory."""

    engine: AsyncEngine
    """Engine used for all database connections."""
    session_factory: async_sessionmaker[AsyncSession]
    """Factory that creates native SQLModel asynchronous sessions."""

    def __init__(self, database_url: str | None = None) -> None:
        """Create database resources for the resolved connection URL."""
        resolved_url = resolve_database_url(database_url)
        self._is_stateless = resolved_url == IN_MEMORY_DATABASE_URL
        engine_kwargs: dict[str, Any] = {}
        if self._is_stateless:
            engine_kwargs["poolclass"] = StaticPool
        self.engine = create_async_engine(resolved_url, **engine_kwargs)
        if self.engine.dialect.name == "sqlite":
            event.listen(
                self.engine.sync_engine,
                "connect",
                _enable_sqlite_foreign_keys,
            )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def is_stateless(self) -> bool:
        """Return whether this instance owns the shared in-memory database."""
        return self._is_stateless

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session and close it without committing caller operations."""
        async with self.session_factory() as session:
            yield session

    async def create_tables(self) -> None:
        """Create all SQLModel tables for databases without migrations."""
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def get_sync_metadata(self, domain: str) -> SyncMetadata | None:
        """Return the synchronization watermark for one domain, if present."""
        async with self.session_factory() as session:
            return await session.get(SyncMetadata, domain)

    async def upsert_sync_metadata(
        self,
        metadata: SyncMetadata,
    ) -> SyncMetadata:
        """Atomically insert or replace one domain synchronization watermark."""
        async with self.session_factory() as session:
            async with session.begin():
                stored = await session.get(SyncMetadata, metadata.domain)
                if stored is None:
                    stored = metadata
                    session.add(stored)
                else:
                    stored.sqlmodel_update(metadata)
                await session.flush()
                session.expunge(stored)
            return stored

    async def record_scheduled_sync_run(
        self,
        run: ScheduledSyncRun,
    ) -> ScheduledSyncRun:
        """Persist and detach the final outcome of one scheduled synchronization."""
        async with self.session_factory() as session:
            async with session.begin():
                session.add(run)
                await session.flush()
                await session.refresh(run)
                session.expunge(run)
            return run

    async def get_latest_scheduled_sync_run(self) -> ScheduledSyncRun | None:
        """Return the most recently started scheduled synchronization, if any."""
        statement = (
            select(ScheduledSyncRun)
            .order_by(cast(QueryableAttribute[Any], ScheduledSyncRun.started_at).desc())
            .limit(1)
        )
        async with self.session_factory() as session:
            result = await session.exec(statement)
            return result.first()

    async def get_database_stats(self) -> dict[str, int]:
        """Return stored record counts across core persistence models."""
        async with self.session_factory() as session:
            txn_count = (
                await session.exec(select(func.count()).select_from(Transaction))
            ).one()
            cat_count = (
                await session.exec(select(func.count()).select_from(Category))
            ).one()
            plaid_count = (
                await session.exec(select(func.count()).select_from(PlaidAccount))
            ).one()
            manual_count = (
                await session.exec(select(func.count()).select_from(ManualAccount))
            ).one()
            tag_count = (
                await session.exec(select(func.count()).select_from(Tag))
            ).one()
            return {
                "transactions": txn_count or 0,
                "categories": cat_count or 0,
                "accounts": (plaid_count or 0) + (manual_count or 0),
                "tags": tag_count or 0,
            }

    async def upsert(self, record: RecordT) -> RecordT:
        """Atomically insert or update one supported record and its owned graph."""
        return (await self.upsert_many((record,)))[0]

    async def upsert_many(
        self,
        records: Iterable[RecordT],
    ) -> list[RecordT]:
        """Atomically persist records in foreign-key-safe dependency order."""
        requested = list(records)
        for record in requested:
            _ensure_supported_record(record)
        ordered = _dependency_order(cast(list[SQLModel], requested))

        if not requested:
            return []

        stored_by_index: dict[int, RecordT] = {}
        async with self.session_factory() as session:
            async with session.begin():
                await _detach_claimed_children(session, requested)
                for _, ordered_record in ordered:
                    await _upsert_record(session, ordered_record)
                await session.flush()
                session.expunge_all()
                for index, record in enumerate(requested):
                    stored = await _load_record(
                        session,
                        type(record),
                        _record_primary_key(record),
                    )
                    if stored is None:
                        msg = (
                            f"Persisted {type(record).__name__} "
                            f"{_record_primary_key(record)} could not be reloaded"
                        )
                        raise RuntimeError(msg)
                    stored_by_index[index] = stored
        return [stored_by_index[index] for index in range(len(requested))]

    async def get(
        self,
        model: type[RecordT],
        primary_key: int,
    ) -> RecordT | None:
        """Return one detached supported record with required relationships loaded."""
        _ensure_supported_model(cast(type[SQLModel], model))
        async with self.session_factory() as session:
            return await _load_record(session, model, primary_key)

    async def list(
        self,
        model: type[RecordT],
    ) -> list[RecordT]:
        """Return all detached records with type-specific relationships loaded."""
        supported_model = cast(type[SQLModel], model)
        _ensure_supported_model(supported_model)
        statement = (
            select(model)
            .options(*_eager_options(supported_model))
            .order_by(_primary_key_attribute(supported_model))
        )
        async with self.session_factory() as session:
            result = await session.exec(statement)
            return list(result.all())

    async def delete(
        self,
        model: type[RecordT],
        primary_key: int,
    ) -> bool:
        """Atomically delete one supported row and report whether it existed."""
        _ensure_supported_model(cast(type[SQLModel], model))
        async with self.session_factory() as session:
            async with session.begin():
                record = await _load_record(session, model, primary_key)
                if record is None:
                    return False
                await session.delete(record)
            return True

    async def __aenter__(self) -> Self:
        """Return this database instance for async context manager use."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Dispose engine resources when leaving an async context manager."""
        await self.dispose()

    async def dispose(self) -> None:
        """Release all connections held by the underlying async engine."""
        await self.engine.dispose()
