"""Service logic for transaction queries and upstream-first mutations."""

import datetime

from sqlalchemy.engine.result import ScalarResult
from sqlmodel import col, select
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from lunchmoney_mcp.database import LunchMoneyDatabase, eager_options
from lunchmoney.models import (
    ChildTransactionObject,
    CreateNewTransactionsRequest,
    DeleteTransactionsRequest,
    GetTransactionAttachmentUrl200Response,
    GroupTransactionsRequest,
    SplitTransactionRequest,
    TransactionAttachmentObject,
    TransactionObject,
    UpdateTransactionObject,
    UpdateTransactionsRequest,
)

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database.models import (
    Category,
    Tag,
    Transaction,
    TransactionAttachment,
    TransactionKind,
)
from lunchmoney_mcp.schemas import TransactionQuery


async def _store_transactions(
    db: LunchMoneyDatabase,
    transactions: list[TransactionObject],
) -> list[TransactionObject]:
    """Persist canonical transaction responses and preserve all their fields."""
    tags = await db.list(Tag)
    records = [
        Transaction.from_api(transaction, tags=tags) for transaction in transactions
    ]
    for record in records:
        await db.upsert(record)
    return transactions


def _normalized_datetime(value: datetime.date | datetime.datetime) -> datetime.datetime:
    """Convert a date or datetime to a comparable UTC timestamp."""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.UTC)
        return value.astimezone(datetime.UTC)
    return datetime.datetime.combine(value, datetime.time.min, tzinfo=datetime.UTC)


def _matches_account_filter(account_id: int | None, filter_value: int | None) -> bool:
    """Apply Lunch Money's account-ID and cash-transaction filter semantics."""
    if filter_value is None:
        return True
    if filter_value == 0:
        return account_id is None
    return account_id == filter_value


def _matches_persisted_transaction(
    transaction: TransactionObject,
    query: TransactionQuery,
    category_ids: set[int],
) -> bool:
    """Apply the upstream transaction filter semantics to one cached object."""
    if query.start_date is not None and transaction.var_date < query.start_date:
        return False
    if query.end_date is not None and transaction.var_date > query.end_date:
        return False
    if query.created_since is not None and _normalized_datetime(
        transaction.created_at
    ) < _normalized_datetime(query.created_since):
        return False
    if query.updated_since is not None and _normalized_datetime(
        transaction.updated_at
    ) < _normalized_datetime(query.updated_since):
        return False
    if not _matches_account_filter(
        account_id=transaction.manual_account_id,
        filter_value=query.manual_account_id,
    ):
        return False
    if not _matches_account_filter(
        account_id=transaction.plaid_account_id,
        filter_value=query.plaid_account_id,
    ):
        return False
    if (
        query.recurring_id is not None
        and transaction.recurring_id != query.recurring_id
    ):
        return False
    if query.category_id == 0 and transaction.category_id is not None:
        return False
    if (
        query.category_id not in (None, 0)
        and transaction.category_id not in category_ids
    ):
        return False
    if query.tag_id is not None and query.tag_id not in transaction.tag_ids:
        return False
    if (
        query.is_group_parent is not None
        and transaction.is_group_parent != query.is_group_parent
    ):
        return False
    if query.status is not None and transaction.status != query.status:
        return False
    if query.is_pending is not None and transaction.is_pending != query.is_pending:
        return False
    if (
        query.is_pending is None
        and query.include_pending is not True
        and transaction.is_pending
    ):
        return False
    return not (query.include_split_parents is not True and transaction.is_split_parent)


def _as_transaction_object(transaction: Transaction) -> TransactionObject:
    """Expose a cached parent or grouped child as a collection response object."""
    api_transaction = transaction.to_api()
    if isinstance(api_transaction, TransactionObject):
        return api_transaction
    return TransactionObject.model_validate(
        {
            **api_transaction.model_dump(mode="python"),
            "children": None,
        }
    )


async def _fetch_persisted_transactions(
    db: LunchMoneyDatabase,
    query: TransactionQuery,
) -> list[TransactionObject]:
    """Return cached parent transactions after applying upstream-compatible filters."""
    category_ids: set[int] = set()
    category_id = query.category_id
    if category_id is not None and category_id != 0:
        category_ids.add(category_id)
        categories = await db.list(Category)
        category_ids.update(
            category.id for category in categories if category.group_id == category_id
        )

    transactions = await db.list(Transaction)
    matching = [
        _as_transaction_object(transaction)
        for transaction in transactions
        if transaction.kind == TransactionKind.PARENT
        or (
            query.include_group_children is True
            and transaction.kind == TransactionKind.CHILD
            and transaction.group_parent_id is not None
        )
    ]
    return sorted(
        (
            transaction
            for transaction in matching
            if _matches_persisted_transaction(
                transaction=transaction,
                query=query,
                category_ids=category_ids,
            )
        ),
        key=lambda transaction: (transaction.var_date, transaction.id),
        reverse=True,
    )


async def fetch_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    query: TransactionQuery,
    live: bool,
) -> list[TransactionObject]:
    """Return every matching transaction from the configured source.

    Stateless servers retrieve every upstream page before responding. Persistent
    servers apply the same filters to the synchronized cache. Both modes return
    every match in one flat collection.
    """
    if live:
        filters = query.model_dump(exclude_none=True)
        transactions = list(
            (
                await client.refresh_transactions(
                    cache=False,
                    **filters,
                )
            ).values()
        )
    else:
        transactions = await _fetch_persisted_transactions(db=db, query=query)

    return transactions


async def fetch_recent_transactions(
    db: LunchMoneyDatabase,
    days: int = 30,
    limit: int = 50,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[TransactionObject]:
    """Fetch bounded cached parent transactions within a reporting period.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.
    days : int
        Number of days back from the resolved end date to include when
        ``start_date`` is omitted. Default is 30.
    limit : int
        Maximum number of transactions to return. Default is 50.
    start_date : datetime.date | None
        Optional inclusive start date for a fixed reporting period.
    end_date : datetime.date | None
        Optional inclusive end date for a fixed reporting period. Defaults to today.

    Returns
    -------
    list[TransactionObject]
        Parent transactions ordered by date descending.
    """
    resolved_end = end_date or datetime.date.today()
    cutoff = start_date or resolved_end - datetime.timedelta(days=days)
    async with db.session() as session:
        statement: SelectOfScalar[Transaction] = (
            select(Transaction)
            .options(*eager_options(Transaction))
            .where(
                Transaction.var_date >= cutoff,
                Transaction.var_date <= resolved_end,
            )
            .where(Transaction.kind == TransactionKind.PARENT)
            .order_by(col(Transaction.var_date).desc())
            .limit(limit)
        )
        results: ScalarResult[Transaction] = await session.exec(statement)
        return [
            transaction
            for transaction in (record.to_api() for record in results.all())
            if isinstance(transaction, TransactionObject)
        ]


async def fetch_transaction_by_id(
    db: LunchMoneyDatabase,
    transaction_id: int,
) -> TransactionObject | ChildTransactionObject | None:
    """Fetch one synchronized transaction by identifier.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.
    transaction_id : int
        Identifier of the transaction to retrieve.

    Returns
    -------
    TransactionObject | ChildTransactionObject | None
        Matching transaction, or ``None`` when it has not been synchronized.
    """
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None:
        return None
    return transaction.to_api()


async def create_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: CreateNewTransactionsRequest,
) -> list[TransactionObject]:
    """Create transactions upstream and cache every canonical response."""
    response = await client.client.transactions_bulk.create_new_transactions(
        create_new_transactions_request=request,
    )
    return await _store_transactions(db=db, transactions=response.transactions)


async def bulk_update_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: UpdateTransactionsRequest,
) -> list[TransactionObject]:
    """Apply a bulk transaction update upstream and cache its responses."""
    response = await client.client.transactions_bulk.update_transactions(
        update_transactions_request=request,
    )
    return await _store_transactions(db=db, transactions=response.transactions)


async def bulk_delete_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: DeleteTransactionsRequest,
) -> None:
    """Delete transactions upstream before removing local cached records."""
    await client.client.transactions_bulk.delete_transactions(
        delete_transactions_request=request,
    )
    for transaction_id in request.ids:
        await db.delete(Transaction, transaction_id)


async def update_transaction(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
    request: UpdateTransactionObject,
    update_balance: bool | None = None,
) -> TransactionObject:
    """Update one transaction upstream and cache Lunch Money's response."""
    transaction = await client.client.transactions.update_transaction(
        id=transaction_id,
        update_transaction_object=request,
        update_balance=update_balance,
    )
    return (await _store_transactions(db=db, transactions=[transaction]))[0]


async def delete_transaction(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
) -> None:
    """Delete one transaction upstream before removing its cached record."""
    await client.client.transactions.delete_transaction_by_id(id=transaction_id)
    await db.delete(Transaction, transaction_id)


async def group_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: GroupTransactionsRequest,
) -> TransactionObject:
    """Create a transaction group upstream and cache its canonical graph."""
    transaction = await client.client.transactions_group.group_transactions(
        group_transactions_request=request,
    )
    return (await _store_transactions(db=db, transactions=[transaction]))[0]


async def ungroup_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
) -> None:
    """Ungroup upstream, then replace cached children with canonical records."""
    group = await db.get(Transaction, transaction_id)
    child_ids = [child.id for child in group.group_children] if group else []
    await client.client.transactions_group.ungroup_transactions(id=transaction_id)
    await db.delete(Transaction, transaction_id)
    restored = [
        await client.client.transactions.get_transaction_by_id(id=child_id)
        for child_id in child_ids
    ]
    if restored:
        await _store_transactions(db=db, transactions=restored)


async def split_transaction(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
    request: SplitTransactionRequest,
) -> TransactionObject:
    """Split a transaction upstream and cache its canonical parent graph."""
    transaction = await client.client.transactions_split.split_transaction(
        id=transaction_id,
        split_transaction_request=request,
    )
    return (await _store_transactions(db=db, transactions=[transaction]))[0]


async def unsplit_transaction(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
) -> None:
    """Unsplit upstream and replace the cached graph with the restored parent."""
    await client.client.transactions_split.unsplit_transaction(id=transaction_id)
    transaction = await client.client.transactions.get_transaction_by_id(
        id=transaction_id
    )
    await db.delete(Transaction, transaction_id)
    await _store_transactions(db=db, transactions=[transaction])


async def upload_transaction_attachment(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    transaction_id: int,
    file: bytes | tuple[str, bytes],
    notes: str | None = None,
) -> TransactionAttachmentObject:
    """Attach a file upstream and append its returned metadata to the cache."""
    attachment = await client.client.transactions_files.attach_file_to_transaction(
        transaction_id=transaction_id,
        file=file,
        notes=notes,
    )
    transaction = await db.get(Transaction, transaction_id)
    if transaction is not None:
        transaction.attachments.append(
            TransactionAttachment.from_api(
                attachment,
                transaction_id=transaction_id,
                position=len(transaction.attachments),
            )
        )
        transaction.files_present = True
        await db.upsert(transaction)
    return attachment


async def fetch_attachment_by_id(
    client: LunchMoneyApp,
    file_id: int,
) -> GetTransactionAttachmentUrl200Response:
    """Fetch Lunch Money's short-lived URL for one transaction attachment."""
    return await client.client.transactions_files.get_transaction_attachment_url(
        file_id=file_id,
    )


async def delete_transaction_attachment(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    file_id: int,
) -> None:
    """Delete an attachment upstream and reconcile its cached owner when known."""
    await client.client.transactions_files.delete_transaction_attachment(
        file_id=file_id
    )
    for transaction in await db.list(Transaction):
        attachments = [
            attachment
            for attachment in transaction.attachments
            if attachment.api_id != file_id
        ]
        if len(attachments) != len(transaction.attachments):
            transaction.attachments = attachments
            transaction.files_present = True
            await db.upsert(transaction)
