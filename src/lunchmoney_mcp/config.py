"""Application configuration and settings using Pydantic Settings."""

from functools import cache
from ipaddress import ip_address
import os
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, CliSettingsSource, SettingsConfigDict

DEFAULT_DATABASE_URL: str = "sqlite+aiosqlite:///lunchmoney.db"
"""Default persistent SQLite connection URL used when omitted."""

IN_MEMORY_DATABASE_URL: str = (
    "sqlite+aiosqlite:///file:memdb?mode=memory&cache=shared&uri=true"
)
"""Shared in-memory SQLite connection URL used by stateless mode."""


def _split_comma_separated_values(value: str) -> tuple[str, ...]:
    """Normalize a comma-separated network policy value.

    Parameters
    ----------
    value : str
        Comma-separated configuration value supplied by the environment or CLI.

    Returns
    -------
    tuple[str, ...]
        Non-empty, whitespace-trimmed policy entries in their configured order.
    """
    return tuple(item.strip() for item in value.split(",") if item.strip())


class SecretSettings(BaseSettings):
    """Environment-only settings that can contain credentials.

    Attributes
    ----------
    access_token : str | None
        Lunch Money API access token.
    mcp_api_key : str | None
        Optional key required by this project's REST API.
    mcp_oauth_client_secret : str | None
        Optional OAuth client secret for confidential identity-provider clients.
    database_url : str
        Database connection URL (sqlite+aiosqlite or postgresql+asyncpg).
    redis_url : str | None
        Redis connection URL for distributed locking.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LUNCHMONEY_",
        extra="ignore",
    )

    access_token: str | None = Field(
        default=None,
        description="Lunch Money API access token",
    )
    """Lunch Money API access token."""

    mcp_api_key: str | None = Field(
        default=None,
        description="Optional API key required by the Lunch Money MCP REST API",
    )
    """Optional API key required by the Lunch Money MCP REST API."""

    mcp_oauth_client_secret: str | None = Field(
        default=None,
        description="Optional OAuth client secret for confidential clients",
    )
    """Optional OAuth client secret for confidential clients."""

    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        description="Database connection URL (sqlite+aiosqlite or postgresql+asyncpg)",
    )
    """Database connection URL."""

    redis_url: str | None = Field(
        default=None,
        description="Redis connection URL for distributed locking",
    )
    """Redis connection URL for distributed locking."""


class RuntimeSettingsBase(BaseSettings):
    """Base model configuration for environment-backed non-secret settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LUNCHMONEY_",
        extra="ignore",
        cli_kebab_case=True,
        cli_implicit_flags=True,
    )


class OAuthSettings(BaseModel):
    """Non-secret OAuth settings shared by the MCP and FastAPI runtimes."""

    mcp_oauth_config_url: str | None = Field(
        default=None,
        description="OIDC discovery URL for remote MCP client authentication",
    )
    """OIDC discovery URL for remote MCP client authentication."""

    mcp_oauth_client_id: str | None = Field(
        default=None,
        description="OAuth client identifier registered with the identity provider",
    )
    """OAuth client identifier registered with the identity provider."""

    mcp_oauth_base_url: str | None = Field(
        default=None,
        description="Public base URL used for OAuth metadata and callback routes",
    )
    """Public base URL used for OAuth metadata and callback routes."""

    mcp_oauth_audience: str | None = Field(
        default=None,
        description="Optional OAuth audience requested from the identity provider",
    )
    """Optional OAuth audience requested from the identity provider."""


class ExecutionSettings(BaseModel):
    """Non-secret settings controlling application execution and synchronization."""

    environment: str = Field(
        default="development",
        description="Application deployment environment",
    )
    """Application deployment environment name."""


class StatelessSettings(BaseModel):
    """Non-secret settings controlling database persistence."""

    stateless: bool = Field(
        default=False,
        description="Run in stateless mode using in-memory SQLite database refreshed from API",
    )
    """Whether to use the shared in-memory database."""

    sync_safety_margin_minutes: int = Field(
        default=5,
        description="Safety overlap margin in minutes for incremental ETL queries",
    )
    """Safety overlap margin for incremental ETL queries."""


class SyncCliSettings(StatelessSettings, RuntimeSettingsBase):
    """CLI-visible settings for one foreground synchronization."""


class ScheduleSettings(BaseModel):
    """Non-secret settings controlling periodic synchronization."""

    schedule_transactions_cron: str | None = Field(
        default=None,
        description="Cron expression used for transaction database synchronization",
    )
    """Cron expression used for transaction database synchronization."""

    schedule_metadata_cron: str | None = Field(
        default=None,
        description="Cron expression used for metadata database synchronization",
    )
    """Cron expression used for metadata database synchronization."""

    schedule_cron: str | None = Field(
        default=None,
        description="Cron expression used by the opt-in scheduler process",
    )
    """Cron expression used by the opt-in scheduler process."""

    schedule_timezone: str = Field(
        default="UTC",
        description="IANA timezone used to interpret the scheduler cron expression",
    )
    """IANA timezone used to interpret the scheduler cron expression."""

    schedule_days: int = Field(
        default=30,
        ge=1,
        description="Rolling transaction window used by the scheduler's initial sync",
    )
    """Rolling transaction window used by the scheduler's initial sync."""


class EmbeddedSchedulerSettings(BaseModel):
    """Non-secret settings controlling FastAPI's local scheduler."""

    embed_scheduler: bool = Field(
        default=False,
        description="Start the local scheduler from the FastAPI application lifespan",
    )
    """Whether a local single-process FastAPI server starts an embedded scheduler."""


class BindSettings(BaseModel):
    """Non-secret settings shared by HTTP MCP and FastAPI servers."""

    host: str = Field(
        default="127.0.0.1",
        description="Interface used by the local FastAPI and HTTP MCP commands",
    )
    """Interface used by the local FastAPI and HTTP MCP commands."""

    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port used by the local FastAPI and HTTP MCP commands",
    )
    """Port used by the local FastAPI and HTTP MCP commands."""

    trusted_proxy_ips: str = Field(
        default="",
        description=(
            "Comma-separated proxy IP addresses trusted to supply forwarding headers; "
            "empty disables proxy trust"
        ),
    )
    """Comma-separated trusted proxy IP addresses; empty disables proxy trust."""

    allowed_hosts: str = Field(
        default="localhost,127.0.0.1",
        description="Comma-separated HTTP Host header allow-list",
    )
    """Comma-separated public hostnames accepted by the HTTP server."""

    cors_allowed_origins: str = Field(
        default="",
        description=(
            "Comma-separated browser origins authorized for CORS; empty disables CORS"
        ),
    )
    """Comma-separated CORS origin allow-list; empty disables CORS."""

    max_request_body_bytes: int = Field(
        default=1_048_576,
        ge=1,
        description="Maximum accepted HTTP request body size in bytes",
    )
    """Maximum accepted HTTP request body size in bytes."""

    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Maximum accepted HTTP request duration in seconds",
    )
    """Maximum accepted HTTP request duration in seconds."""

    max_concurrent_requests: int = Field(
        default=100,
        ge=1,
        description="Maximum in-flight HTTP requests per process",
    )
    """Maximum in-flight HTTP requests accepted by a process."""

    rate_limit_requests: int = Field(
        default=120,
        ge=1,
        description="Maximum requests per client in each rate-limit window",
    )
    """Maximum requests accepted from one client during the rate-limit window."""

    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        description="Fixed rate-limit window duration in seconds",
    )
    """Duration of the fixed rate-limit window in seconds."""

    @field_validator("trusted_proxy_ips")
    @classmethod
    def _validate_trusted_proxy_ips(cls, value: str) -> str:
        """Accept only explicit proxy IP addresses for forwarding-header trust."""
        addresses = _split_comma_separated_values(value)
        for address in addresses:
            ip_address(address)
        return ",".join(addresses)

    @field_validator("allowed_hosts")
    @classmethod
    def _validate_allowed_hosts(cls, value: str) -> str:
        """Require a concrete Host header allow-list without wildcards."""
        hosts = _split_comma_separated_values(value)
        if not hosts:
            msg = "allowed_hosts must contain at least one host"
            raise ValueError(msg)
        if "*" in hosts:
            msg = "allowed_hosts must not contain a wildcard"
            raise ValueError(msg)
        return ",".join(hosts)

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_cors_allowed_origins(cls, value: str) -> str:
        """Normalize CORS origins while refusing the insecure wildcard origin."""
        origins = _split_comma_separated_values(value)
        if "*" in origins:
            msg = "cors_allowed_origins must not contain a wildcard"
            raise ValueError(msg)
        return ",".join(origins)

    @property
    def trusted_proxy_ip_list(self) -> tuple[str, ...]:
        """Return the proxy IP allow-list in middleware-friendly form."""
        return _split_comma_separated_values(self.trusted_proxy_ips)

    @property
    def allowed_host_list(self) -> tuple[str, ...]:
        """Return the HTTP Host header allow-list in middleware-friendly form."""
        return _split_comma_separated_values(self.allowed_hosts)

    @property
    def cors_allowed_origin_list(self) -> tuple[str, ...]:
        """Return the CORS origin allow-list in middleware-friendly form."""
        return _split_comma_separated_values(self.cors_allowed_origins)


class RuntimeSettings(
    OAuthSettings,
    ExecutionSettings,
    StatelessSettings,
    ScheduleSettings,
    EmbeddedSchedulerSettings,
    BindSettings,
    RuntimeSettingsBase,
):
    """All non-secret environment settings used by application components."""


class McpCliSettings(OAuthSettings, BindSettings, RuntimeSettingsBase):
    """CLI-visible settings for the standalone MCP runtime."""


class ScheduleCliSettings(
    StatelessSettings,
    ScheduleSettings,
    RuntimeSettingsBase,
):
    """CLI-visible settings for the dedicated scheduler runtime."""


class ServeCliSettings(
    OAuthSettings,
    ExecutionSettings,
    StatelessSettings,
    ScheduleSettings,
    EmbeddedSchedulerSettings,
    BindSettings,
    RuntimeSettingsBase,
):
    """CLI-visible settings for the local FastAPI runtime."""


_runtime_settings: RuntimeSettings | None = None
"""Process-local runtime settings supplied by Pydantic's CLI parser."""

RuntimeMode = Literal["mcp", "schedule", "serve", "sync"]
"""The dedicated runtime command currently executing in this process."""

_runtime_mode: RuntimeMode | None = None
"""Process-local runtime mode used to enforce command-level responsibilities."""


CliSettings = McpCliSettings | ScheduleCliSettings | ServeCliSettings | SyncCliSettings
"""A command-specific model that exposes only that command's safe CLI flags."""


def parse_cli_settings(
    arguments: list[str],
    settings_type: type[CliSettings],
    root_parser: Any | None = None,
) -> RuntimeSettings:
    """Parse runtime options with Pydantic Settings' native CLI source.

    Parameters
    ----------
    arguments : list[str]
        Kebab-case Pydantic Settings arguments without an executable or subcommand.
    settings_type : type[CliSettings]
        Command-specific model defining the safe options accepted by this entry point.
    root_parser : Any | None
        Optional parser with runtime-specific arguments that Pydantic extends with
        Settings options before parsing.

    Returns
    -------
    RuntimeSettings
        Complete non-secret configuration populated from the command's CLI flags,
        environment variables, and `.env`.
    """
    source: Any = CliSettingsSource(
        settings_type,
        cli_parse_args=arguments,
        root_parser=root_parser,
    )
    cli_settings = cast(Any, settings_type)(_cli_settings_source=source)
    return RuntimeSettings.model_validate(cli_settings.model_dump(exclude_unset=True))


def configure_runtime_settings(settings: RuntimeSettings) -> None:
    """Make CLI-parsed settings available to the current runtime process.

    Parameters
    ----------
    settings : RuntimeSettings
        Configuration parsed before the FastAPI or scheduler runtime starts.
    """
    global _runtime_settings
    _runtime_settings = settings
    get_settings.cache_clear()


def configure_runtime_mode(mode: RuntimeMode) -> None:
    """Record the command mode that owns the current process.

    Parameters
    ----------
    mode : RuntimeMode
        Runtime command selected by the executable.
    """
    global _runtime_mode
    _runtime_mode = mode


def get_runtime_mode() -> RuntimeMode | None:
    """Return the command mode selected for the current process.

    Returns
    -------
    RuntimeMode | None
        Selected runtime mode, or ``None`` outside the executable dispatcher.
    """
    return _runtime_mode


def export_runtime_settings(settings: RuntimeSettings) -> None:
    """Expose non-default runtime settings to a Uvicorn reloader child.

    Parameters
    ----------
    settings : RuntimeSettings
        Resolved runtime configuration. Only values supplied by a configuration
        source are exported; defaults remain defaults in the child process.
    """
    for field_name in settings.model_fields_set:
        environment_name = f"LUNCHMONEY_{field_name.upper()}"
        value = getattr(settings, field_name)
        if value is None:
            os.environ.pop(environment_name, None)
        elif isinstance(value, bool):
            os.environ[environment_name] = str(value).lower()
        else:
            os.environ[environment_name] = str(value)


@cache
def get_settings() -> RuntimeSettings:
    """Return cached non-secret runtime settings.

    Returns
    -------
    RuntimeSettings
        Cached non-secret configuration populated from a runtime CLI or environment.
    """
    return _runtime_settings or RuntimeSettings()


@cache
def get_secret_settings() -> SecretSettings:
    """Return cached environment-only secret settings."""
    return SecretSettings()
