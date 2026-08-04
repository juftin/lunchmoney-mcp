"""Service logic for Accounts data operations."""

import datetime

from lunchmoney.models import (
    ManualAccountObject,
)

from lunchmoney_mcp.client import LunchMoneyApp
from lunchmoney_mcp.database import LunchMoneyDatabase
from lunchmoney_mcp.database.models import ManualAccount, PlaidAccount, Transaction
from lunchmoney_mcp.schemas import (
    AccountInfo,
    AccountsSummary,
    ManualAccountCreateRequest,
    ManualAccountUpdateRequest,
)


def _manual_account_info(account: ManualAccount) -> AccountInfo:
    """Convert one persisted manual account into the public response schema."""
    return AccountInfo(
        id=account.id,
        name=account.name,
        display_name=account.display_name,
        balance=float(account.balance),
        currency=account.currency,
        type_or_status=account.type,
        institution_name=account.institution_name,
    )


async def fetch_accounts(db: LunchMoneyDatabase) -> AccountsSummary:
    """Fetch all connected Plaid and manual accounts with current balances.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.

    Returns
    -------
    AccountsSummary
        Combined summary of connected Plaid and manual accounts.
    """
    plaid_accs = await db.list(PlaidAccount)
    manual_accs = await db.list(ManualAccount)
    return AccountsSummary(
        plaid_accounts=[
            AccountInfo(
                id=a.id,
                name=a.name,
                display_name=a.display_name,
                institution_name=a.institution_name,
                balance=float(a.balance),
                currency=a.currency,
                type_or_status=a.type,
            )
            for a in plaid_accs
        ],
        manual_accounts=[_manual_account_info(account) for account in manual_accs],
    )


async def fetch_manual_account_by_id(
    db: LunchMoneyDatabase,
    account_id: int,
) -> AccountInfo | None:
    """Fetch one synchronized manual account by identifier.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.
    account_id : int
        Identifier of the manual account to retrieve.

    Returns
    -------
    AccountInfo | None
        Matching manual account, or ``None`` when it has not been synchronized.
    """
    account = await db.get(ManualAccount, account_id)
    if account is None:
        return None
    return _manual_account_info(account)


async def fetch_plaid_account_by_id(
    db: LunchMoneyDatabase,
    account_id: int,
) -> AccountInfo | None:
    """Fetch one synchronized Plaid account by identifier.

    Parameters
    ----------
    db : LunchMoneyDatabase
        Database manager instance.
    account_id : int
        Identifier of the Plaid account to retrieve.

    Returns
    -------
    AccountInfo | None
        Matching Plaid account, or ``None`` when it has not been synchronized.
    """
    account = await db.get(PlaidAccount, account_id)
    if account is None:
        return None
    return AccountInfo(
        id=account.id,
        name=account.name,
        display_name=account.display_name,
        balance=float(account.balance),
        currency=account.currency,
        type_or_status=account.type,
        institution_name=account.institution_name,
    )


async def _store_manual_account(
    db: LunchMoneyDatabase,
    account: ManualAccountObject,
) -> AccountInfo:
    """Persist an upstream manual-account response and expose public fields."""
    stored = await db.upsert(ManualAccount.from_api(account))
    return _manual_account_info(stored)


async def create_manual_account(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    request: ManualAccountCreateRequest,
) -> AccountInfo:
    """Create a manual account upstream before saving its canonical response.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    db : LunchMoneyDatabase
        Database manager that stores the canonical response.
    request : ManualAccountCreateRequest
        Validated manual-account fields supplied by an API or MCP caller.

    Returns
    -------
    AccountInfo
        Created manual account after its local cache has been updated.
    """
    account = await client.client.manual_accounts.create_manual_account(
        create_manual_account_request_object=request.to_api(),
    )
    return await _store_manual_account(db=db, account=account)


async def update_manual_account(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    account_id: int,
    request: ManualAccountUpdateRequest,
) -> AccountInfo:
    """Update a manual account upstream before saving its canonical response.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    db : LunchMoneyDatabase
        Database manager that stores the canonical response.
    account_id : int
        Identifier of the manual account to update.
    request : ManualAccountUpdateRequest
        Validated fields to update.

    Returns
    -------
    AccountInfo
        Updated manual account after its local cache has been updated.
    """
    account = await client.client.manual_accounts.update_manual_account(
        id=account_id,
        update_manual_account_request_object=request.to_api(),
    )
    return await _store_manual_account(db=db, account=account)


async def delete_manual_account(
    client: LunchMoneyApp,
    db: LunchMoneyDatabase,
    account_id: int,
    delete_items: bool | None = None,
    delete_balance_history: bool | None = None,
) -> None:
    """Delete a manual account upstream before removing its cached record.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    db : LunchMoneyDatabase
        Database manager that removes the stale cached row.
    account_id : int
        Identifier of the manual account to delete.
    delete_items : bool | None
        Whether Lunch Money should delete related transactions and rules.
    delete_balance_history : bool | None
        Whether Lunch Money should delete associated balance history.
    """
    await client.client.manual_accounts.delete_manual_account(
        id=account_id,
        delete_items=delete_items,
        delete_balance_history=delete_balance_history,
    )
    transactions = await db.list(Transaction)
    affected_transactions = [
        transaction
        for transaction in transactions
        if transaction.manual_account_id == account_id
    ]
    if delete_items:
        for transaction in affected_transactions:
            await db.delete(Transaction, transaction.id)
    else:
        for transaction in affected_transactions:
            transaction.manual_account_id = None
        if affected_transactions:
            await db.upsert_many(affected_transactions)
    await db.delete(ManualAccount, account_id)


async def trigger_plaid_fetch(
    client: LunchMoneyApp,
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    account_id: int | None = None,
) -> None:
    """Ask Lunch Money to fetch recent Plaid transactions.

    Parameters
    ----------
    client : LunchMoneyApp
        Configured Lunch Money API client.
    start_date : datetime.date | None
        Optional inclusive start of the transaction fetch window.
    end_date : datetime.date | None
        Optional inclusive end of the transaction fetch window.
    account_id : int | None
        Optional Plaid account identifier; omitting it fetches eligible accounts.
    """
    await client.client.plaid.trigger_plaid_account_fetch(
        start_date=start_date,
        end_date=end_date,
        id=account_id,
    )
