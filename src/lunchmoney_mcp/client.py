"""
Client classes for LunchMoneyApp
"""

import asyncio
import datetime
import logging
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass, field
from functools import cached_property
from os import getenv
from typing import Any, Callable, ClassVar, NamedTuple, TypeVar, overload

import lunchmoney
from lunchmoney import GetAllTransactions200Response
from lunchmoney.models import (
    BudgetSettingsResponseObject,
    CategoryObject,
    ChildCategoryObject,
    ManualAccountObject,
    PlaidAccountObject,
    SummaryResponseObject,
    TagObject,
    TransactionObject,
    UserObject,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


LunchableModelType = TypeVar("LunchableModelType", bound=BaseModel)


class LunchableModels:
    """
    Container for Lunchable Data Model Types
    """

    PlaidAccountObject: ClassVar[type[PlaidAccountObject]] = PlaidAccountObject
    """Plaid Accounts"""
    TransactionObject: ClassVar[type[TransactionObject]] = TransactionObject
    """Transactions"""
    CategoryObject: ClassVar[type[CategoryObject]] = CategoryObject
    """Categories"""
    ManualAccountObject: ClassVar[type[ManualAccountObject]] = ManualAccountObject
    """Manual Accounts"""
    TagObject: ClassVar[type[TagObject]] = TagObject
    """Tags"""
    UserObject: ClassVar[type[UserObject]] = UserObject
    """User"""


models: type[LunchableModels] = LunchableModels
"""Container for Lunchable Data Model Types"""


@dataclass(slots=True)
class SyncSummary:
    """Summary of records synced to the database."""

    user: int = 0
    plaid_accounts: int = 0
    manual_accounts: int = 0
    categories: int = 0
    tags: int = 0
    transactions: int = 0

    @property
    def total(self) -> int:
        """Total number of records persisted."""
        return (
            self.user
            + self.plaid_accounts
            + self.manual_accounts
            + self.categories
            + self.tags
            + self.transactions
        )


@dataclass(slots=True)
class LunchableData:
    """
    Data Container for Lunchable App Data
    """

    plaid_accounts: dict[int, PlaidAccountObject] = field(default_factory=dict)
    """Plaid Accounts"""
    transactions: dict[int, TransactionObject] = field(default_factory=dict)
    """Transactions"""
    categories: dict[int, CategoryObject] = field(default_factory=dict)
    """Categories"""
    manual_accounts: dict[int, ManualAccountObject] = field(default_factory=dict)
    """Manual Accounts"""
    tags: dict[int, TagObject] = field(default_factory=dict)
    """Tags"""
    user: UserObject | None = None
    """User"""
    budget_settings: BudgetSettingsResponseObject | None = None
    """Budget Settings"""
    summaries: dict[tuple[Any, ...], SummaryResponseObject] = field(
        default_factory=dict
    )
    """Budget Summaries keyed by query arguments"""

    def clear(self) -> None:
        """
        Clear all stored data
        """
        self.plaid_accounts.clear()
        self.transactions.clear()
        self.categories.clear()
        self.manual_accounts.clear()
        self.tags.clear()
        self.user = None
        self.budget_settings = None
        self.summaries.clear()

    @property
    def category_map(self) -> dict[int, CategoryObject | ChildCategoryObject]:
        """
        Category Mapping Across Parent and Child Categories

        Returns
        -------
        dict[int, Union[PlaidAccountObject, ManualAccountObject]]
        """
        child_categories: dict[int, ChildCategoryObject] = {
            child.id: child
            for category in self.categories.values()
            for child in category.children or []
        }
        return {**self.categories, **child_categories}

    @property
    def current_user(self) -> UserObject:
        """
        Current User Object

        Returns
        -------
        UserObject
        """
        if not self.user:
            raise ValueError("User data has not been loaded.")
        return self.user

    @property
    def asset_map(self) -> dict[int, PlaidAccountObject | ManualAccountObject]:
        """
        Asset Mapping Across Plaid Accounts and Assets

        Returns
        -------
        dict[int, Union[PlaidAccountObject, ManualAccountObject]]
        """
        return {
            **self.plaid_accounts,
            **self.manual_accounts,
        }

    @property
    def plaid_accounts_list(self) -> list[PlaidAccountObject]:
        """
        List of Plaid Accounts

        Returns
        -------
        list[PlaidAccountObject]
        """
        return list(self.plaid_accounts.values())

    @property
    def manual_accounts_list(self) -> list[ManualAccountObject]:
        """
        List of Manual Accounts

        Returns
        -------
        list[ManualAccountObject]
        """
        return list(self.manual_accounts.values())

    @property
    def transactions_list(self) -> list[TransactionObject]:
        """
        List of Transactions

        Returns
        -------
        list[TransactionObject]
        """
        return list(self.transactions.values())

    @property
    def categories_list(self) -> list[CategoryObject]:
        """
        List of Categories

        Returns
        -------
        list[CategoryObject]
        """
        return list(self.categories.values())

    @property
    def tags_list(self) -> list[TagObject]:
        """
        List of Tags

        Returns
        -------
        list[TagObject]
        """
        return list(self.tags.values())


class _ObjectMapper(NamedTuple):
    """
    Object Mapper for Lunchable Models
    """

    func: Callable[..., Any]
    data_attr: str


class LunchableClient:
    """
    API Container for Lunchable App APIs
    """

    def __init__(self, access_token: str | None = None) -> None:
        """Initialize the LunchableApi container.

        Parameters
        ----------
        access_token: str | None
            LunchMoney Access Token. If not provided, will attempt to read from
            `LUNCHMONEY_ACCESS_TOKEN` environment variable.
        """
        access_token = access_token or getenv("LUNCHMONEY_ACCESS_TOKEN")
        if not access_token:
            raise ValueError(
                "LunchMoney API key must be provided via "
                "parameter or LUNCHMONEY_ACCESS_TOKEN environment "
                "variable."
            )
        self.configuration = lunchmoney.Configuration(
            host="https://api.lunchmoney.dev/v2", access_token=access_token
        )
        self.api_client: lunchmoney.ApiClient = lunchmoney.ApiClient(
            configuration=self.configuration
        )

    @cached_property
    def budgets(self) -> lunchmoney.BudgetsApi:
        """BudgetsApi client instance."""
        return lunchmoney.BudgetsApi(api_client=self.api_client)

    @cached_property
    def categories(self) -> lunchmoney.CategoriesApi:
        """CategoriesApi client instance."""
        return lunchmoney.CategoriesApi(api_client=self.api_client)

    @cached_property
    def manual_accounts(self) -> lunchmoney.ManualAccountsApi:
        """ManualAccountsApi client instance."""
        return lunchmoney.ManualAccountsApi(api_client=self.api_client)

    @cached_property
    def me(self) -> lunchmoney.MeApi:
        """MeApi client instance for user-related operations."""
        return lunchmoney.MeApi(api_client=self.api_client)

    @cached_property
    def plaid(self) -> lunchmoney.PlaidAccountsApi:
        """PlaidAccountsApi client instance."""
        return lunchmoney.PlaidAccountsApi(api_client=self.api_client)

    @cached_property
    def recurring_items(self) -> lunchmoney.RecurringItemsApi:
        """RecurringItemsApi client instance."""
        return lunchmoney.RecurringItemsApi(api_client=self.api_client)

    @cached_property
    def summary(self) -> lunchmoney.SummaryApi:
        """SummaryApi client instance."""
        return lunchmoney.SummaryApi(api_client=self.api_client)

    @cached_property
    def tags(self) -> lunchmoney.TagsApi:
        """TagsApi client instance."""
        return lunchmoney.TagsApi(api_client=self.api_client)

    @cached_property
    def transactions(self) -> lunchmoney.TransactionsApi:
        """TransactionsApi client instance."""
        return lunchmoney.TransactionsApi(api_client=self.api_client)

    @cached_property
    def transactions_bulk(self) -> lunchmoney.TransactionsBulkApi:
        """TransactionsBulkApi client instance used for bulk operations."""
        return lunchmoney.TransactionsBulkApi(api_client=self.api_client)

    @cached_property
    def transactions_files(self) -> lunchmoney.TransactionsFilesApi:
        """TransactionsFilesApi client instance for handling attachments."""
        return lunchmoney.TransactionsFilesApi(api_client=self.api_client)

    @cached_property
    def transactions_group(self) -> lunchmoney.TransactionsGroupApi:
        """TransactionsGroupApi client instance for grouping operations."""
        return lunchmoney.TransactionsGroupApi(api_client=self.api_client)

    @cached_property
    def transactions_split(self) -> lunchmoney.TransactionsSplitApi:
        """TransactionsSplitApi client instance for split transactions."""
        return lunchmoney.TransactionsSplitApi(api_client=self.api_client)


class LunchMoneyApp:
    """
    Base LunchMoney App Class
    """

    models: ClassVar[type[LunchableModels]] = LunchableModels
    """Container for Lunchable Data Model Types"""
    lunchable_models: ClassVar[Iterable[type[BaseModel]]] = [
        PlaidAccountObject,
        CategoryObject,
        ManualAccountObject,
        TagObject,
        UserObject,
    ]
    """Every LunchableApp should define which data objects it depends on"""
    lunchable_models_kwargs: ClassVar[dict[type[BaseModel], dict[str, Any]]] = {}
    """Optional keyword arguments to pass to model constructors (supports callables)"""
    transaction_pagination: ClassVar[int] = 500
    """Number of Transactions to fetch per page during pagination"""

    def __init__(
        self,
        access_token: str | None = None,
        lunchable_models: Iterable[type[BaseModel]] | None = None,
        lunchable_models_kwargs: dict[type[BaseModel], dict[str, Any]] | None = None,
        transaction_pagination: int | None = None,
        cache: bool = True,
    ) -> None:
        """
        Initialize LunchMoneyApp

        Parameters
        ----------
        access_token: str | None
            LunchMoney Access Token. If not provided, will attempt to read from
            `LUNCHMONEY_ACCESS_TOKEN` environment variable.
        lunchable_models: Iterable[type[LunchableModelType]] | None
            Explicit list of Lunchable Models to use in this app. If not provided,
            will default to the class variable `lunchable_models`.
        lunchable_models_kwargs: dict[type[LunchableModelType], dict[str, Any]] | None
            Optional keyword arguments to pass to model constructors. If not provided,
            will default to the class variable `lunchable_models_kwargs`.
        transaction_pagination: int | None
            Number of Transactions to fetch per page during pagination. If not provided,
            will default to the class variable `transaction_pagination`.
        cache: bool
            Whether refresh operations store data on this app instance by default.
        """
        self.client: LunchableClient = LunchableClient(access_token=access_token)
        self.data: LunchableData = LunchableData()
        self._lunchable_models: Iterable[type[BaseModel]] = (
            lunchable_models or self.__class__.lunchable_models
        )
        self._lunchable_models_kwargs: dict[type[BaseModel], dict[str, Any]] = (
            lunchable_models_kwargs or self.__class__.lunchable_models_kwargs
        )
        self._transaction_pagination: int = (
            transaction_pagination or self.__class__.transaction_pagination
        )
        self.cache: bool = cache

    @cached_property
    def _model_mapping(self) -> dict[type[BaseModel], _ObjectMapper]:
        """
        Model Class -> _ObjectMapper Mapping
        """
        return {
            PlaidAccountObject: _ObjectMapper(
                func=self.client.plaid.get_all_plaid_accounts,
                data_attr="plaid_accounts",
            ),
            TransactionObject: _ObjectMapper(
                func=self.client.transactions_bulk.get_all_transactions,
                data_attr="transactions",
            ),
            CategoryObject: _ObjectMapper(
                func=self.client.categories.get_all_categories,
                data_attr="categories",
            ),
            ManualAccountObject: _ObjectMapper(
                func=self.client.manual_accounts.get_all_manual_accounts,
                data_attr="manual_accounts",
            ),
            TagObject: _ObjectMapper(
                func=self.client.tags.get_all_tags,
                data_attr="tags",
            ),
            UserObject: _ObjectMapper(
                func=self.client.me.get_me,
                data_attr="me",
            ),
        }

    def _get_model_mapper(self, model: type[LunchableModelType]) -> _ObjectMapper:
        """
        Get the appropriate function for a given Lunchable Model

        Parameters
        ----------
        model: Type[LunchableModelType]
            Type of Lunchable Model to get the function for

        Returns
        -------
        _ObjectMapper
            _ObjectMapper containing the function and data attribute name
        """
        mapper = self._model_mapping.get(model)
        if not mapper:
            msg = f"Model {model.__name__} is not supported for refresh."
            raise NotImplementedError(msg)
        return mapper

    def _resolve_model_kwargs(
        self, model: type[LunchableModelType], **kwargs: Any
    ) -> dict[str, Any]:
        """
        Resolve Any Model Kwargs that Are Callable
        """
        model_kwargs = self._lunchable_models_kwargs.get(model, {}).copy()
        model_kwargs.update(kwargs)
        resolved_kwargs: dict[str, Any] = {}
        for key, value in model_kwargs.items():
            if callable(value):
                resolved_value = value()
            else:
                resolved_value = value
            resolved_kwargs[key] = resolved_value
        return resolved_kwargs

    @overload
    async def refresh(
        self, model: type[UserObject], cache: bool | None = None, **kwargs: Any
    ) -> UserObject: ...

    @overload
    async def refresh(
        self, model: type[TransactionObject], cache: bool | None = None, **kwargs: Any
    ) -> dict[int, TransactionObject]: ...

    @overload
    async def refresh(
        self, model: type[LunchableModelType], cache: bool | None = None, **kwargs: Any
    ) -> dict[int, LunchableModelType]: ...

    async def refresh(
        self, model: type[LunchableModelType], cache: bool | None = None, **kwargs: Any
    ) -> LunchableModelType | dict[int, LunchableModelType]:
        """
        Refresh a Lunchable Model

        Parameters
        ----------
        model: Type[LunchableModelType]
            Type of Lunchable Model to refresh
        cache: bool | None
            Whether to store refreshed data on this app instance. If omitted,
            uses this instance's `cache` default.
        kwargs: Any
            Additional keyword arguments to pass to the function that
            fetches the data.

        Returns
        -------
        LunchableModelType | dict[int, LunchableModelType]
            Unless you're requesting the `UserObject`, this method will return a
            dictionary of the refreshed data, keyed by the object's ID.

        Examples
        --------
        ```python
        from lunchable.models import CategoriesObject
        from lunchable.plugins import LunchableApp

        app = LunchableApp()
        categories: dict[int, CategoriesObject] = app.refresh(CategoriesObject)
        ```
        """
        cache = self.cache if cache is None else cache
        mapper = self._get_model_mapper(model)
        model_kwargs = self._resolve_model_kwargs(model=model, **kwargs)
        logger.info("Refreshing LunchMoney Data: %s", mapper.data_attr)
        if model is UserObject:
            user = await mapper.func(**model_kwargs)
            if cache:
                self.data.user = user
            return user
        elif model is TransactionObject:
            transaction_map: dict[int, TransactionObject] = {
                obj.id: obj async for obj in self._paginate_transactions(**model_kwargs)
            }
            logger.info("Refreshed LunchMoney Transactions (%s)", len(transaction_map))
            if cache:
                self.data.transactions.update(transaction_map)
            return transaction_map  # type: ignore[return-value]
        else:
            response = await mapper.func(**model_kwargs)
            data_dict = {obj.id: obj for obj in getattr(response, mapper.data_attr)}
            if cache:
                setattr(self.data, mapper.data_attr, data_dict)
            return data_dict

    async def refresh_data(
        self,
        models: Iterable[type[LunchableModelType]] | None = None,
        cache: bool | None = None,
    ) -> None:
        """
        Refresh the data in the Lunchable App

        Parameters
        ----------
        models: Iterable[type[LunchableModelType]] | None
            Explicit list of Lunchable Models to refresh. If not provided,
            all models defined in will be refreshed (which by default is
            all of them except for transactions)
        cache: bool | None
            Whether to store refreshed data on this app instance. If omitted,
            uses this instance's `cache` default.

        Examples
        --------
        ```python
        from lunchable.models import PlaidAccountObject
        from lunchable.plugins import LunchableApp

        app = LunchableApp()
        app.refresh_data()
        plaid_accounts: dict[int, PlaidAccountObject] = app.data.plaid_accounts
        ```

        ```python
        from lunchable.models import AssetsObject
        from lunchable.plugins import LunchableApp

        app = LunchableApp()
        app.refresh_data(models=[AssetsObject])
        assets: dict[int, AssetsObject] = app.data.assets
        ```
        """
        cache = self.cache if cache is None else cache
        refresh_models = models or self._lunchable_models
        await asyncio.gather(
            *[self.refresh(model, cache=cache) for model in set(refresh_models)]
        )

    async def refresh_transactions(
        self,
        start_date: datetime.date | None = None,
        end_date: datetime.date | None = None,
        created_since: datetime.date | str | None = None,
        updated_since: datetime.date | str | None = None,
        manual_account_id: int | None = None,
        plaid_account_id: int | None = None,
        recurring_id: int | None = None,
        category_id: int | None = None,
        tag_id: int | None = None,
        is_group_parent: bool | None = None,
        status: str | None = None,
        is_pending: bool | None = None,
        include_pending: bool | None = None,
        include_metadata: bool | None = None,
        include_split_parents: bool | None = None,
        include_group_children: bool | None = None,
        include_children: bool | None = None,
        include_files: bool | None = None,
        cache: bool | None = None,
    ) -> dict[int, TransactionObject]:
        """
        Refresh Transactions in the App

        Parameters
        ----------
        start_date: datetime.date | None
            Denotes the beginning of the time period to fetch transactions for. If
            omitted, the most recent transactions will be returned. See `limit`.
            Required if end_date exists.
        end_date: datetime.date | None
            Denotes the end of the time period you'd like to get transactions for.
            Required if start_date exists.
        created_since: datetime.date | str | None
            Filter transactions to those created after the specified timestamp.
            Accepts either a date (YYYY-MM-DD) or ISO 8601 datetime string.
            Date-only values are interpreted as midnight UTC (00:00:00Z).
        updated_since: datetime.date | str | None
            Filter transactions to those updated after the specified timestamp.
            Accepts either a date (YYYY-MM-DD) or ISO 8601 datetime string.
            Date-only values are interpreted as midnight UTC (00:00:00Z).
        manual_account_id: int | None
            Filter transactions to those associated with specified manual account ID
            or set this to 0 to omit any transactions from manual accounts. Setting
            both this and `plaid_account_id` to 0 will return transactions with no
            account. These are listed as "Cash Transactions" in the Lunch Money GUI.
            Note that transaction groups are not associated with any account. If you
            want the response to include transactions from transaction groups, set
            the `include_group_children` query parameter to `true` when filtering
            by manual accounts.
        plaid_account_id: int | None
            Filter transactions to those associated with specified plaid account ID
            or set this to 0 to omit any transactions from plaid accounts. Setting
            both this and `manual_account_id` to 0 will return transactions with no
            account. These are listed as "Cash Transactions" in the Lunch Money GUI.
            Note that transaction groups are not associated with any account. If you
            want the response to include transactions from transaction groups, set
            the `include_group_children` query parameter to `true` when filtering
            by plaid accounts.
        recurring_id: int | None
            Filter transactions to those associated with specified Recurring Item ID
        category_id: int | None
            Filter transactions to those associated with the specified category ID.
            Will also match category groups. Set this to 0 to return only
            un-categorized transactions.
        tag_id: int | None
            Filter transactions to those that have a tag with the specified Tag ID.
        is_group_parent: bool | None
            Filter by group (returns only transaction groups if `true`).
        status: str | None
            Filter transactions to those with the specified status:
            - `reviewed`: Only user reviewed transactions or those that were
              automatically marked as reviewed due to reviewed recurring_item logic
            - `unreviewed`: Only transactions that need to be reviewed
            - `delete_pending`: Only transactions that require manual intervention
              because the plaid account deleted this transaction after it was
              updated by the user.
        is_pending: bool | None
            Filter transactions by pending status. Set to `true` to return only
            pending transactions, or `false` to return only non-pending
            transactions. When this parameter is set, it takes precedence over
            `include_pending`. Note: Pending transactions always have a status of
            `unreviewed`, so when setting this parameter to `true`, either omit the
            `status` parameter or set it to `unreviewed`.
        include_pending: bool | None
            By default, pending transactions are excluded from results. Set to
            `true` to include imported transactions with a pending status in the
            results. This query param is ignored if the `is_pending` query param is
            also set.
        include_metadata: bool | None
            By default, custom and plaid metadata are not included in the response.
            Set to true if you'd like the returned transactions objects to include
            any metadata associated with the transactions.
        include_split_parents: bool | None
            By default, transactions that were split into multiple transactions are
            not included in the response. Set to true if you'd like the returned
            transactions objects to include any transactions that were split into
            multiple transactions. Use with caution as this data is normally not
            exposed after the split transactions are created.
        include_group_children: bool | None
            By default, individual transactions that joined into a transaction group
            are not included in the response. Set to true if you'd like the returned
            transactions objects to include any transactions that joined into a
            transaction group.
        include_children: bool | None
            Whether returned parent transactions include their split or grouped
            child records.
        include_files: bool | None
            By default, the `files` property is not included in the response. Set to
            true if you'd like the responses to include a list of objects that
            describe any files attached to the transactions.
        cache: bool | None
            Whether to store refreshed data on this app instance. If omitted,
            uses this instance's `cache` default.

        Returns
        -------
        dict[int, TransactionObject]
            Dictionary of Transactions keyed by Transaction ID
        """
        cache = self.cache if cache is None else cache
        kwargs: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "created_since": created_since,
            "updated_since": updated_since,
            "manual_account_id": manual_account_id,
            "plaid_account_id": plaid_account_id,
            "recurring_id": recurring_id,
            "category_id": category_id,
            "tag_id": tag_id,
            "is_group_parent": is_group_parent,
            "status": status,
            "is_pending": is_pending,
            "include_pending": include_pending,
            "include_metadata": include_metadata,
            "include_split_parents": include_split_parents,
            "include_group_children": include_group_children,
            "include_children": include_children,
            "include_files": include_files,
        }
        filtered_kwargs: dict[str, Any] = {
            k: v for k, v in kwargs.items() if v is not None
        }
        transaction_map: dict[int, TransactionObject] = {
            obj.id: obj async for obj in self._paginate_transactions(**filtered_kwargs)
        }
        logger.info("Refreshed LunchMoney Transactions (%s)", len(transaction_map))
        if cache:
            self.data.transactions.update(transaction_map)
        return transaction_map

    async def _paginate_transactions(
        self, **kwargs: Any
    ) -> AsyncIterable[TransactionObject]:
        """
        Paginate Transactions from the App
        """
        offset = 0
        while True:
            paginated_kwargs: dict[str, Any] = {
                **kwargs,
                "offset": offset,
                "limit": self._transaction_pagination,
            }
            response: GetAllTransactions200Response = (
                await self.client.transactions_bulk.get_all_transactions(
                    **paginated_kwargs
                )
            )
            for transaction in response.transactions:
                yield transaction
            if not response.has_more:
                break
            offset += self._transaction_pagination

    def clear_transactions(self) -> None:
        """
        Clear Transactions from the App
        """
        self.data.transactions.clear()


__all__ = [
    # Data Model Types
    "PlaidAccountObject",
    "TransactionObject",
    "CategoryObject",
    "ManualAccountObject",
    "TagObject",
    "UserObject",
    # Module Exports
    "LunchableModels",
    "models",
    "LunchableData",
    "LunchableClient",
    "LunchMoneyApp",
    "SyncSummary",
]
