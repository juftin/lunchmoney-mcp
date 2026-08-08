"""Services package containing reusable domain business logic."""

from lunchmoney_mcp.services.accounts import (
    create_manual_account,
    delete_manual_account,
    fetch_accounts,
    fetch_manual_account_by_id,
    fetch_manual_accounts,
    fetch_plaid_account_by_id,
    fetch_plaid_accounts,
    trigger_plaid_fetch,
    update_manual_account,
)
from lunchmoney_mcp.services.budgets import (
    clear_budget_value,
    fetch_budget_settings,
    set_budget_value,
)
from lunchmoney_mcp.services.categories import (
    create_category,
    delete_category,
    fetch_categories,
    fetch_category_by_id,
    update_category,
)
from lunchmoney_mcp.services.dashboard import fetch_dashboard_data
from lunchmoney_mcp.services.recurring import (
    fetch_recurring_item_by_id,
    fetch_recurring_items,
)
from lunchmoney_mcp.services.spending import (
    fetch_category_spending,
    fetch_spending_trends,
)
from lunchmoney_mcp.services.summary import fetch_account_summary
from lunchmoney_mcp.services.sync import (
    execute_mcp_sync,
    execute_sync,
    get_scheduled_sync_status,
    run_scheduled_sync,
)
from lunchmoney_mcp.services.tags import (
    create_tag,
    delete_tag,
    fetch_tag_by_id,
    fetch_tags,
    update_tag,
)
from lunchmoney_mcp.services.transactions import (
    bulk_delete_transactions,
    bulk_update_transactions,
    create_transactions,
    delete_transaction,
    delete_transaction_attachment,
    fetch_attachment_by_id,
    fetch_recent_transactions,
    fetch_transactions,
    fetch_transaction_by_id,
    group_transactions,
    split_transaction,
    ungroup_transactions,
    unsplit_transaction,
    update_transaction,
    upload_transaction_attachment,
)
from lunchmoney_mcp.services.user import fetch_user_info

__all__ = [
    "execute_mcp_sync",
    "execute_sync",
    "get_scheduled_sync_status",
    "run_scheduled_sync",
    "fetch_account_summary",
    "fetch_budget_settings",
    "clear_budget_value",
    "fetch_accounts",
    "fetch_categories",
    "fetch_category_by_id",
    "fetch_category_spending",
    "fetch_dashboard_data",
    "fetch_spending_trends",
    "fetch_manual_account_by_id",
    "fetch_manual_accounts",
    "fetch_plaid_account_by_id",
    "fetch_plaid_accounts",
    "fetch_transactions",
    "fetch_recent_transactions",
    "fetch_recurring_item_by_id",
    "fetch_recurring_items",
    "fetch_tag_by_id",
    "fetch_tags",
    "create_tag",
    "update_tag",
    "delete_tag",
    "fetch_transaction_by_id",
    "fetch_user_info",
    "create_category",
    "update_category",
    "delete_category",
    "bulk_delete_transactions",
    "bulk_update_transactions",
    "create_transactions",
    "delete_transaction",
    "delete_transaction_attachment",
    "fetch_attachment_by_id",
    "group_transactions",
    "split_transaction",
    "ungroup_transactions",
    "unsplit_transaction",
    "update_transaction",
    "upload_transaction_attachment",
    "create_manual_account",
    "update_manual_account",
    "delete_manual_account",
    "trigger_plaid_fetch",
    "set_budget_value",
]
