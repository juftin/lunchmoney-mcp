"""Service logic for transaction queries and upstream-first mutations."""

from sqlalchemy.engine.result import ScalarResult
from typing import Sequence
from sqlmodel.sql._expression_select_cls import SelectOfScalar

import datetime

from sqlmodel import col, select

from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney.models import (
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
from lunchmoney_mcp.database.models import Tag, Transaction, TransactionAttachment
from lunchmoney_mcp.schemas import TransactionInfo


def _transaction_info(transaction: Transaction) -> TransactionInfo:
    """Convert one persisted transaction into its public response schema."""
    return TransactionInfo(
        id=transaction.id,
        date=transaction.var_date,
        payee=transaction.payee,
        amount=float(transaction.amount),
        currency=transaction.currency,
        category_id=transaction.category_id,
        notes=transaction.notes,
        status=transaction.status,
    )


async def _store_transactions(
    db: LunchMoneyDatabase,
    transactions: list[TransactionObject],
) -> list[TransactionInfo]:
    """Persist canonical transaction responses and return their public fields."""
    tags = await db.list(Tag)
    records = [
        Transaction.from_api(transaction, tags=tags) for transaction in transactions
    ]
    stored = [await db.upsert(record) for record in records]
    return [_transaction_info(transaction) for transaction in stored]


async def fetch_recent_transactions(
    db: LunchMoneyDatabase,
    days: int = 30,
    limit: int = 50,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
) -> list[TransactionInfo]:
    """Fetch recent transactions from local database within specified date window.

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
    list[TransactionInfo]
        Filtered list of matching transaction objects ordered by date descending.
    """
    resolved_end = end_date or datetime.date.today()
    cutoff = start_date or resolved_end - datetime.timedelta(days=days)
    async with db.session() as session:
        statement: SelectOfScalar[Transaction] = (
            select(Transaction)
            .where(
                Transaction.var_date >= cutoff,
                Transaction.var_date <= resolved_end,
            )
            .order_by(col(Transaction.var_date).desc())
            .limit(limit)
        )
        results: ScalarResult[Transaction] = await session.exec(statement)
        txns: Sequence[Transaction] = results.all()
        return [_transaction_info(transaction) for transaction in txns]


async def fetch_transaction_by_id(
    db: LunchMoneyDatabase,
    transaction_id: int,
) -> TransactionInfo | None:
    """Fetch one synchronized transaction by identifier.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.
    transaction_id : int
        Identifier of the transaction to retrieve.

    Returns
    -------
    TransactionInfo | None
        Matching transaction, or ``None`` when it has not been synchronized.
    """
    transaction = await db.get(Transaction, transaction_id)
    if transaction is None:
        return None
    return _transaction_info(transaction)


async def create_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: CreateNewTransactionsRequest,
) -> list[TransactionInfo]:
    """Create transactions upstream and cache every canonical response."""
    response = await client.client.transactions_bulk.create_new_transactions(
        create_new_transactions_request=request,
    )
    return await _store_transactions(db=db, transactions=response.transactions)


async def bulk_update_transactions(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: UpdateTransactionsRequest,
) -> list[TransactionInfo]:
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
) -> TransactionInfo:
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
) -> TransactionInfo:
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
) -> TransactionInfo:
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
