"""
Pydantic schemas and response models for FastAPI endpoints and MCP tools.
"""

import datetime
from typing import Any, Literal

from lunchmoney.models import (
    AccountTypeEnum,
    CreateManualAccountRequestObject,
    CreateManualAccountRequestObjectBalance,
    CreateManualAccountRequestObjectClosedOn,
    CurrencyEnum,
    ManualAccountObject,
    PlaidAccountObject,
    UpdateManualAccountRequestObject,
    UpdateManualAccountRequestObjectBalance,
    UpdateManualAccountRequestObjectClosedOn,
)
from pydantic import BaseModel, Field


class RootResponse(BaseModel):
    """Health check / root endpoint response schema."""

    message: str = Field(default="Hello World", description="Status message")
    """Status message returned by the health check endpoint."""


class SyncDetails(BaseModel):
    """Counts of records synchronized per model."""

    user: int = Field(description="User records synced")
    """Number of user profile records synchronized."""
    plaid_accounts: int = Field(description="Plaid accounts synced")
    """Number of Plaid account records synchronized."""
    manual_accounts: int = Field(description="Manual accounts synced")
    """Number of manual account records synchronized."""
    categories: int = Field(description="Categories synced")
    """Number of category records synchronized."""
    tags: int = Field(description="Tags synced")
    """Number of tag records synchronized."""
    transactions: int = Field(description="Transactions synced")
    """Number of transaction records synchronized."""
    total: int = Field(description="Total records synchronized")
    """Aggregate count of all synchronized database objects."""


class SyncResponse(BaseModel):
    """FastAPI POST /api/sync response schema."""

    message: str = Field(default="Synchronization complete")
    """Status message summarizing synchronization execution."""
    synced: SyncDetails
    """Detailed count of synchronized records by model."""


class UserInfo(BaseModel):
    """User profile details."""

    id: int
    """Unique identifier for the Lunch Money user."""
    name: str
    """User's display name."""
    email: str
    """User's email address."""
    budget_name: str
    """Title of the user's primary budget."""
    primary_currency: str
    """Three-letter ISO currency code of the user's primary budget."""


class CategoryInfo(BaseModel):
    """Budget category details."""

    id: int
    """Unique category identifier."""
    name: str
    """Category display name."""
    is_income: bool
    """Whether the category represents income rather than an expense."""
    exclude_from_budget: bool
    """Whether the category is excluded from budget calculations."""
    exclude_from_totals: bool
    """Whether the category is excluded from financial totals."""
    is_group: bool
    """Whether this category acts as a parent category group."""
    group_id: int | None = None
    """Optional identifier of the parent category group."""


class TagInfo(BaseModel):
    """Transaction tag details."""

    id: int
    """Unique tag identifier."""
    name: str
    """Tag display name."""
    description: str | None = None
    """Optional tag description."""
    text_color: str | None = None
    """Optional text color used to display the tag."""
    background_color: str | None = None
    """Optional background color used to display the tag."""
    archived: bool
    """Whether the tag is archived."""


class AccountInfo(BaseModel):
    """Financial account details."""

    id: int
    """Unique account identifier."""
    name: str
    """Account display name."""
    display_name: str | None = None
    """Optional user-facing account name, preferred when present."""
    balance: float
    """Current account balance."""
    currency: str
    """Three-letter ISO currency code for the account balance."""
    type_or_status: str | None = None
    """Account status (Plaid) or account type (Manual)."""
    institution_name: str | None = None
    """Name of the financial institution hosting the account."""


class AccountsSummary(BaseModel):
    """Complete synchronized manual and Plaid account collections."""

    plaid_accounts: list[PlaidAccountObject] = Field(default_factory=list)
    """Complete objects for connected Plaid accounts."""
    manual_accounts: list[ManualAccountObject] = Field(default_factory=list)
    """Complete objects for user-managed manual accounts."""


class TransactionQuery(BaseModel):
    """Upstream-compatible transaction filters and pagination controls."""

    start_date: datetime.date | None = None
    """Inclusive transaction-date lower bound."""
    end_date: datetime.date | None = None
    """Inclusive transaction-date upper bound."""
    created_since: datetime.datetime | datetime.date | None = None
    """Inclusive ISO 8601 creation timestamp lower bound."""
    updated_since: datetime.datetime | datetime.date | None = None
    """Inclusive ISO 8601 update timestamp lower bound."""
    manual_account_id: int | None = None
    """Manual-account filter; zero selects transactions without one."""
    plaid_account_id: int | None = None
    """Plaid-account filter; zero selects transactions without one."""
    recurring_id: int | None = None
    """Recurring-item identifier to match."""
    category_id: int | None = None
    """Category identifier to match; zero selects uncategorized transactions."""
    tag_id: int | None = None
    """Tag identifier to match."""
    is_group_parent: bool | None = None
    """Optional group-parent state to match."""
    status: str | None = None
    """Optional Lunch Money transaction status to match."""
    is_pending: bool | None = None
    """Optional pending state to match."""
    include_pending: bool | None = None
    """Whether to include pending transactions when not filtering by pending state."""
    include_metadata: bool | None = None
    """Whether the live upstream request includes transaction metadata."""
    include_split_parents: bool | None = None
    """Whether to include transactions that have split children."""
    include_group_children: bool | None = None
    """Whether the live upstream request includes grouped child transactions."""
    include_children: bool | None = None
    """Whether the live upstream request includes nested transaction children."""
    include_files: bool | None = None
    """Whether the live upstream request includes transaction attachments."""


class CategoryQuery(BaseModel):
    """Upstream-compatible category collection filters."""

    format: Literal["nested", "flattened"] | None = None
    """Category hierarchy representation; omitted uses Lunch Money's default."""
    is_group: bool | None = None
    """Whether to return category groups or ungrouped non-group categories."""


class ManualAccountCreateRequest(BaseModel):
    """User-facing fields accepted when creating a manual account."""

    name: str
    """User-defined account name."""
    type: AccountTypeEnum
    """Manual account type recognized by Lunch Money."""
    balance: float | str
    """Current numeric balance, represented as a number or decimal string."""
    institution_name: str | None = None
    """Optional financial institution name."""
    display_name: str | None = None
    """Optional name displayed to the user."""
    subtype: str | None = None
    """Optional manual account subtype."""
    balance_as_of: str | None = None
    """Optional ISO-8601 timestamp at which the balance was measured."""
    currency: CurrencyEnum | None = None
    """Optional balance currency."""
    status: str | None = "active"
    """Initial account lifecycle status."""
    closed_on: datetime.date | None = None
    """Optional date on which the account was closed."""
    external_id: str | None = None
    """Optional caller-defined external identifier."""
    custom_metadata: dict[str, Any] | None = None
    """Optional arbitrary JSON metadata stored with the account."""
    exclude_from_transactions: bool | None = False
    """Whether the account is excluded from transaction assignment."""

    def to_api(self) -> CreateManualAccountRequestObject:
        """Convert this HTTP/MCP request into the generated client model."""
        values = self.model_dump(exclude_none=True)
        values["balance"] = CreateManualAccountRequestObjectBalance.model_construct(
            actual_instance=self.balance,
        )
        if self.closed_on is not None:
            values["closed_on"] = (
                CreateManualAccountRequestObjectClosedOn.model_construct(
                    actual_instance=self.closed_on,
                )
            )
        return CreateManualAccountRequestObject(**values)


class ManualAccountUpdateRequest(BaseModel):
    """User-facing fields accepted when updating a manual account."""

    name: str | None = None
    """Updated user-defined account name."""
    institution_name: str | None = None
    """Updated financial institution name."""
    display_name: str | None = None
    """Updated name displayed to the user."""
    type: AccountTypeEnum | None = None
    """Updated manual account type."""
    subtype: str | None = None
    """Updated manual account subtype."""
    balance: float | str | None = None
    """Updated numeric balance, represented as a number or decimal string."""
    currency: CurrencyEnum | None = None
    """Updated balance currency."""
    balance_as_of: str | None = None
    """Updated ISO-8601 timestamp at which the balance was measured."""
    status: str | None = None
    """Updated account lifecycle status."""
    closed_on: datetime.date | None = None
    """Updated closure date; explicitly set null clears it upstream."""
    external_id: str | None = None
    """Updated caller-defined external identifier."""
    custom_metadata: dict[str, Any] | None = None
    """Updated arbitrary JSON metadata."""
    exclude_from_transactions: bool | None = None
    """Updated transaction assignment exclusion policy."""

    def to_api(self) -> UpdateManualAccountRequestObject:
        """Convert this HTTP/MCP request into the generated client model."""
        values = self.model_dump(exclude_unset=True)
        if "balance" in values:
            values["balance"] = UpdateManualAccountRequestObjectBalance.model_construct(
                actual_instance=self.balance,
            )
        if "closed_on" in values:
            values["closed_on"] = (
                UpdateManualAccountRequestObjectClosedOn.model_construct(
                    actual_instance=self.closed_on,
                )
            )
        return UpdateManualAccountRequestObject(**values)


class TransactionInfo(BaseModel):
    """Transaction summary item."""

    id: int
    """Unique transaction identifier."""
    date: datetime.date
    """Date on which the transaction occurred."""
    payee: str
    """Payee or merchant name."""
    amount: float
    """Transaction amount in original currency."""
    currency: str
    """Three-letter ISO currency code of the transaction."""
    category_id: int | None = None
    """Optional identifier of the assigned category."""
    notes: str | None = None
    """Optional notes attached to the transaction."""
    status: str
    """Transaction review status (cleared, uncleared, etc.)."""


class TransactionAttachmentUploadRequest(BaseModel):
    """File content and optional metadata for a transaction attachment."""

    file: bytes
    """Raw file content, encoded as base64 when supplied through JSON."""
    filename: str | None = None
    """Optional original filename retained by Lunch Money."""
    notes: str | None = None
    """Optional user-visible notes describing the attachment."""

    def to_api_file(self) -> bytes | tuple[str, bytes]:
        """Return the generated client's accepted multipart file value."""
        if self.filename is None:
            return self.file
        return (self.filename, self.file)


class SyncResult(BaseModel):
    """MCP tool sync_data response schema."""

    status: str = Field(default="success")
    """Overall status of the sync operation."""
    synced_records: SyncDetails
    """Detailed breakdown of synchronized record counts."""


class ScheduledSyncStatus(BaseModel):
    """Persisted result of the latest attempted scheduled synchronization."""

    status: Literal["success", "failed", "skipped"]
    """Final state of the scheduler attempt."""
    started_at: datetime.datetime
    """UTC timestamp at which the scheduler attempted the sync."""
    finished_at: datetime.datetime
    """UTC timestamp at which the scheduler recorded its final result."""
    message: str | None = None
    """Safe operator-facing explanation for a failed or skipped run."""
    synced: SyncDetails | None = None
    """Record counts returned by a successful synchronization, when available."""


class SyncStatusSummary(BaseModel):
    """Synchronization status and engine environment metadata for dashboard display."""

    persistence_mode: str
    """Data persistence mode (e.g. Persistent (SQLite), Stateless (In-Memory))."""
    db_driver: str = "sqlite+aiosqlite"
    """Database driver / dialect name (e.g. sqlite+aiosqlite)."""
    db_url: str = "sqlite+aiosqlite:///:memory:"
    """Sanitized database connection URL with credentials masked."""
    stored_transactions: int = 0
    """Total transaction records persisted in local database."""
    stored_categories: int = 0
    """Total category records persisted in local database."""
    stored_accounts: int = 0
    """Total account records (Plaid + manual) persisted in local database."""
    stored_tags: int = 0
    """Total tag records persisted in local database."""

    # Workload 1: Transactions Database Sync
    transaction_cron: str | None = None
    """Cron expression for transaction database sync."""
    transaction_timezone: str | None = None
    """Timezone for transaction sync schedule."""
    transaction_last_synced_at: datetime.datetime | None = None
    """Watermark timestamp for transaction sync."""
    transaction_next_sync_at: datetime.datetime | None = None
    """Calculated next transaction sync timestamp."""

    # Workload 2: Metadata Database Sync (Accounts, Categories, Tags, User)
    metadata_cron: str | None = None
    """Cron expression for metadata database sync (Accounts, Categories, Tags, User)."""
    metadata_timezone: str | None = None
    """Timezone for metadata sync schedule."""
    metadata_last_synced_at: datetime.datetime | None = None
    """Watermark timestamp for metadata sync."""
    metadata_next_sync_at: datetime.datetime | None = None
    """Calculated next metadata sync timestamp."""

    last_synced_at: datetime.datetime | None = None
    """Most recent transaction watermark or completed sync timestamp."""
    schedule_cron: str | None = None
    """Configured cron expression for scheduled sync workloads."""
    schedule_timezone: str | None = None
    """Configured timezone for interpreting the sync cron expression."""
    next_sync_at: datetime.datetime | None = None
    """Calculated next scheduled synchronization timestamp."""
    embed_scheduler: bool = False
    """Whether local scheduler is embedded in the FastAPI application lifespan."""
    scheduled_sync: ScheduledSyncStatus | None = None
    """Latest recorded outcome of scheduled synchronization."""


class ChildCategorySpending(BaseModel):
    """Spending breakdown for a child category."""

    category_id: int
    """Unique child category identifier."""
    category_name: str
    """Child category display name."""
    is_income: bool
    """Whether child category represents income."""
    total_amount: float
    """Total net transaction amount for this child category."""
    transaction_count: int
    """Number of transactions for this child category."""


class CategorySpending(BaseModel):
    """Category spending summary with rollup parent/child aggregation."""

    category_id: int
    """Category identifier (or -1 for Uncategorized)."""
    category_name: str
    """Category display name."""
    is_group: bool
    """Whether category is a parent category group."""
    is_income: bool
    """Whether category represents income."""
    total_amount: float
    """Total net transaction amount including child category rollups."""
    transaction_count: int
    """Total number of transactions including child category rollups."""
    children: list[ChildCategorySpending] = Field(default_factory=list)
    """Breakdown of spending for nested child categories, if any."""


class GroupedSpendingResponse(BaseModel):
    """Grouped spending response by category over specified date range."""

    start_date: datetime.date
    """Start date of the spending analysis window."""
    end_date: datetime.date
    """End date of the spending analysis window."""
    total_spending: float
    """Aggregate spending total across expense categories."""
    total_income: float
    """Aggregate income total across income categories."""
    categories: list[CategorySpending] = Field(default_factory=list)
    """Category spending rollups grouped by top-level category."""


class SpendingTrendPoint(BaseModel):
    """One time-series bucket of categorized spending activity."""

    start_date: datetime.date
    """Inclusive calendar date on which this bucket begins."""
    total_spending: float
    """Aggregate expense amount in this bucket."""
    total_income: float
    """Aggregate income amount in this bucket."""
    transaction_count: int
    """Number of included transactions in this bucket."""


class SpendingTrendsResponse(BaseModel):
    """Time-series spending analysis over a requested transaction window."""

    start_date: datetime.date
    """Inclusive start date of the analyzed transaction window."""
    end_date: datetime.date
    """Inclusive end date of the analyzed transaction window."""
    granularity: Literal["daily", "weekly", "monthly"]
    """Calendar period used to group transactions into trend points."""
    trends: list[SpendingTrendPoint] = Field(default_factory=list)
    """Chronologically ordered spending trend points."""
