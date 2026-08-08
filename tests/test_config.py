"""Tests for application configuration and Pydantic Settings."""

import os
from pathlib import Path

import pytest

from lunchmoney_mcp.config import (
    DEFAULT_DATABASE_URL,
    IN_MEMORY_DATABASE_URL,
    McpCliSettings,
    RuntimeSettings,
    ScheduleCliSettings,
    SecretSettings,
    ServeCliSettings,
    SyncCliSettings,
    configure_runtime_mode,
    export_runtime_settings,
    get_secret_settings,
    get_settings,
    parse_cli_settings,
)
from lunchmoney_mcp.database import resolve_database_url


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve default settings when environment variables are omitted.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest environment monkeypatching fixture.
    """
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    monkeypatch.delenv("LUNCHMONEY_REDIS_URL", raising=False)
    monkeypatch.delenv("LUNCHMONEY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_API_KEY", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_OAUTH_CONFIG_URL", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_OAUTH_BASE_URL", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MCP_OAUTH_AUDIENCE", raising=False)
    monkeypatch.delenv("LUNCHMONEY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("LUNCHMONEY_STATELESS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_SYNC_SAFETY_MARGIN_MINUTES", raising=False)
    monkeypatch.delenv("LUNCHMONEY_SCHEDULE_CRON", raising=False)
    monkeypatch.delenv("LUNCHMONEY_SCHEDULE_TIMEZONE", raising=False)
    monkeypatch.delenv("LUNCHMONEY_SCHEDULE_DAYS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_EMBED_SCHEDULER", raising=False)
    monkeypatch.delenv("LUNCHMONEY_HOST", raising=False)
    monkeypatch.delenv("LUNCHMONEY_PORT", raising=False)
    monkeypatch.delenv("LUNCHMONEY_TRUSTED_PROXY_IPS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MAX_REQUEST_BODY_BYTES", raising=False)
    monkeypatch.delenv("LUNCHMONEY_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_MAX_CONCURRENT_REQUESTS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_RATE_LIMIT_REQUESTS", raising=False)
    monkeypatch.delenv("LUNCHMONEY_RATE_LIMIT_WINDOW_SECONDS", raising=False)

    secret_settings = SecretSettings()
    settings = RuntimeSettings()
    assert secret_settings.database_url == DEFAULT_DATABASE_URL
    assert secret_settings.redis_url is None
    assert secret_settings.access_token is None
    assert secret_settings.mcp_api_key is None
    assert secret_settings.mcp_oauth_client_secret is None
    assert settings.mcp_oauth_config_url is None
    assert settings.mcp_oauth_client_id is None
    assert settings.mcp_oauth_base_url is None
    assert settings.mcp_oauth_audience is None
    assert settings.stateless is False
    assert settings.sync_safety_margin_minutes == 5
    assert settings.schedule_transactions_cron is None
    assert settings.schedule_metadata_cron is None
    assert settings.schedule_cron is None
    assert settings.schedule_timezone == "UTC"
    assert settings.schedule_days == 30
    assert settings.embed_scheduler is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.trusted_proxy_ips == ""
    assert settings.trusted_proxy_ip_list == ()
    assert settings.allowed_hosts == "localhost,127.0.0.1"
    assert settings.allowed_host_list == ("localhost", "127.0.0.1")
    assert settings.cors_allowed_origins == ""
    assert settings.cors_allowed_origin_list == ()
    assert settings.max_request_body_bytes == 1_048_576
    assert settings.request_timeout_seconds == 30.0
    assert settings.max_concurrent_requests == 100
    assert settings.rate_limit_requests == 120
    assert settings.rate_limit_window_seconds == 60


def test_settings_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override settings values via environment variables.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Pytest environment monkeypatching fixture.
    """
    monkeypatch.setenv(
        "LUNCHMONEY_DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db"
    )
    monkeypatch.setenv("LUNCHMONEY_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("LUNCHMONEY_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("LUNCHMONEY_MCP_API_KEY", "rest-api-key")
    monkeypatch.setenv(
        "LUNCHMONEY_MCP_OAUTH_CONFIG_URL",
        "https://id.example.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("LUNCHMONEY_MCP_OAUTH_CLIENT_ID", "lunchmoney-mcp")
    monkeypatch.setenv("LUNCHMONEY_MCP_OAUTH_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("LUNCHMONEY_MCP_OAUTH_BASE_URL", "https://mcp.example.com")
    monkeypatch.setenv("LUNCHMONEY_MCP_OAUTH_AUDIENCE", "https://mcp.example.com")
    monkeypatch.setenv("LUNCHMONEY_STATELESS", "true")
    monkeypatch.setenv("LUNCHMONEY_SYNC_SAFETY_MARGIN_MINUTES", "10")
    monkeypatch.setenv("LUNCHMONEY_SCHEDULE_CRON", "15 4 * * 1-5")
    monkeypatch.setenv("LUNCHMONEY_SCHEDULE_TIMEZONE", "America/Denver")
    monkeypatch.setenv("LUNCHMONEY_SCHEDULE_DAYS", "45")
    monkeypatch.setenv("LUNCHMONEY_EMBED_SCHEDULER", "true")
    monkeypatch.setenv("LUNCHMONEY_HOST", "0.0.0.0")
    monkeypatch.setenv("LUNCHMONEY_PORT", "9000")
    monkeypatch.setenv("LUNCHMONEY_TRUSTED_PROXY_IPS", "10.0.0.2, 2001:db8::1")
    monkeypatch.setenv("LUNCHMONEY_ALLOWED_HOSTS", "api.example.com, mcp.example.com")
    monkeypatch.setenv(
        "LUNCHMONEY_CORS_ALLOWED_ORIGINS",
        "https://app.example.com, https://admin.example.com",
    )
    monkeypatch.setenv("LUNCHMONEY_MAX_REQUEST_BODY_BYTES", "2097152")
    monkeypatch.setenv("LUNCHMONEY_REQUEST_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LUNCHMONEY_MAX_CONCURRENT_REQUESTS", "25")
    monkeypatch.setenv("LUNCHMONEY_RATE_LIMIT_REQUESTS", "30")
    monkeypatch.setenv("LUNCHMONEY_RATE_LIMIT_WINDOW_SECONDS", "15")

    secret_settings = SecretSettings()
    settings = RuntimeSettings()
    assert secret_settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"
    assert secret_settings.redis_url == "redis://localhost:6379/0"
    assert secret_settings.access_token == "test-token"
    assert secret_settings.mcp_api_key == "rest-api-key"
    assert (
        settings.mcp_oauth_config_url
        == "https://id.example.com/.well-known/openid-configuration"
    )
    assert settings.mcp_oauth_client_id == "lunchmoney-mcp"
    assert secret_settings.mcp_oauth_client_secret == "synthetic-secret"
    assert settings.mcp_oauth_base_url == "https://mcp.example.com"
    assert settings.mcp_oauth_audience == "https://mcp.example.com"
    assert settings.stateless is True
    assert settings.sync_safety_margin_minutes == 10
    assert settings.schedule_cron == "15 4 * * 1-5"
    assert settings.schedule_timezone == "America/Denver"
    assert settings.schedule_days == 45
    assert settings.embed_scheduler is True
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.trusted_proxy_ips == "10.0.0.2,2001:db8::1"
    assert settings.trusted_proxy_ip_list == ("10.0.0.2", "2001:db8::1")
    assert settings.allowed_hosts == "api.example.com,mcp.example.com"
    assert settings.allowed_host_list == ("api.example.com", "mcp.example.com")
    assert settings.cors_allowed_origin_list == (
        "https://app.example.com",
        "https://admin.example.com",
    )
    assert settings.max_request_body_bytes == 2_097_152
    assert settings.request_timeout_seconds == 45.0
    assert settings.max_concurrent_requests == 25
    assert settings.rate_limit_requests == 30
    assert settings.rate_limit_window_seconds == 15


def test_settings_parse_runtime_cli_arguments() -> None:
    """Parse scheduler, embedded-server, and bind options from kebab-case CLI flags."""
    settings = parse_cli_settings(
        [
            "--schedule-cron",
            "15 4 * * 1-5",
            "--schedule-timezone",
            "America/Denver",
            "--schedule-days",
            "45",
            "--embed-scheduler",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--trusted-proxy-ips",
            "10.0.0.2",
            "--allowed-hosts",
            "api.example.com",
            "--cors-allowed-origins",
            "https://app.example.com",
            "--max-request-body-bytes",
            "2097152",
            "--request-timeout-seconds",
            "45",
            "--max-concurrent-requests",
            "25",
            "--rate-limit-requests",
            "30",
            "--rate-limit-window-seconds",
            "15",
        ],
        ServeCliSettings,
    )

    assert settings.schedule_cron == "15 4 * * 1-5"
    assert settings.schedule_timezone == "America/Denver"
    assert settings.schedule_days == 45
    assert settings.embed_scheduler is True
    assert settings.host == "0.0.0.0"
    assert settings.port == 9000
    assert settings.trusted_proxy_ip_list == ("10.0.0.2",)
    assert settings.allowed_host_list == ("api.example.com",)
    assert settings.cors_allowed_origin_list == ("https://app.example.com",)
    assert settings.max_request_body_bytes == 2_097_152
    assert settings.request_timeout_seconds == 45.0
    assert settings.max_concurrent_requests == 25
    assert settings.rate_limit_requests == 30
    assert settings.rate_limit_window_seconds == 15


def test_cli_settings_prefer_flags_over_environment_and_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Resolve a command's CLI flags before environment variables and `.env` values."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LUNCHMONEY_HOST=dotenv-host\n")
    monkeypatch.setenv("LUNCHMONEY_HOST", "environment-host")

    settings = parse_cli_settings(["--host", "cli-host"], McpCliSettings)

    assert settings.host == "cli-host"


def test_cli_help_only_exposes_lowercase_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Expose safe lowercase runtime options without secret settings."""
    with pytest.raises(SystemExit):
        parse_cli_settings(["--help"], ServeCliSettings)

    help_output = capsys.readouterr().out
    assert "--schedule-cron" in help_output
    assert "--sync-safety-margin-minutes" in help_output
    assert "--access-token" not in help_output
    assert "--mcp-api-key" not in help_output
    assert "--mcp-oauth-client-secret" not in help_output
    assert "--database-url" not in help_output
    assert "--redis-url" not in help_output
    assert "--LUNCHMONEY-SYNC-SAFETY-MARGIN-MINUTES" not in help_output


def test_cli_rejects_secret_options() -> None:
    """Prevent credentials from being accepted as command-line arguments."""
    with pytest.raises(SystemExit):
        parse_cli_settings(
            ["--access-token", "synthetic-secret"],
            ServeCliSettings,
        )


def test_runtime_cli_options_share_mcp_transport_host_and_port() -> None:
    """Use the runtime host and port flags with an HTTP MCP transport."""
    from lunchmoney_mcp.mcp.server import create_argument_parser

    settings = parse_cli_settings(
        ["--streamable-http", "--host", "0.0.0.0", "--port", "9000"],
        McpCliSettings,
        root_parser=create_argument_parser(),
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 9000


def test_mcp_help_makes_the_stdio_default_explicit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Describe the default MCP transport in the command's generated help."""
    from lunchmoney_mcp.mcp.server import create_argument_parser

    with pytest.raises(SystemExit):
        create_argument_parser().parse_args(["--help"])

    assert "standard input/output transport (default)" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("settings_type", "expected", "unexpected"),
    [
        (McpCliSettings, "--host", "--schedule-cron"),
        (ScheduleCliSettings, "--schedule-cron", "--mcp-oauth-client-id"),
        (ServeCliSettings, "--embed-scheduler", "--access-token"),
        (SyncCliSettings, "--sync-safety-margin-minutes", "--access-token"),
    ],
)
def test_command_cli_help_only_shows_relevant_options(
    capsys: pytest.CaptureFixture[str],
    settings_type: type[
        McpCliSettings | ScheduleCliSettings | ServeCliSettings | SyncCliSettings
    ],
    expected: str,
    unexpected: str,
) -> None:
    """Show each entry point only the safe flags it can use."""
    with pytest.raises(SystemExit):
        parse_cli_settings(["--help"], settings_type)

    help_output = capsys.readouterr().out
    assert expected in help_output
    assert unexpected not in help_output


def test_export_runtime_settings_preserves_cli_values_for_reloader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Export explicit runtime values into the environment inherited by reloaders."""
    monkeypatch.delenv("LUNCHMONEY_EMBED_SCHEDULER", raising=False)
    monkeypatch.delenv("LUNCHMONEY_HOST", raising=False)
    monkeypatch.delenv("LUNCHMONEY_PORT", raising=False)
    settings = RuntimeSettings(
        embed_scheduler=True,
        host="0.0.0.0",
        port=9000,
    )

    export_runtime_settings(settings)

    assert os.environ["LUNCHMONEY_EMBED_SCHEDULER"] == "true"
    assert os.environ["LUNCHMONEY_HOST"] == "0.0.0.0"
    assert os.environ["LUNCHMONEY_PORT"] == "9000"


def test_export_runtime_settings_preserves_network_policy_for_reloader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Export configured network policy values into a reloader child process."""
    for environment_name in (
        "LUNCHMONEY_TRUSTED_PROXY_IPS",
        "LUNCHMONEY_ALLOWED_HOSTS",
        "LUNCHMONEY_CORS_ALLOWED_ORIGINS",
        "LUNCHMONEY_MAX_REQUEST_BODY_BYTES",
        "LUNCHMONEY_REQUEST_TIMEOUT_SECONDS",
        "LUNCHMONEY_MAX_CONCURRENT_REQUESTS",
        "LUNCHMONEY_RATE_LIMIT_REQUESTS",
        "LUNCHMONEY_RATE_LIMIT_WINDOW_SECONDS",
    ):
        monkeypatch.delenv(environment_name, raising=False)
    settings = RuntimeSettings(
        trusted_proxy_ips="10.0.0.2",
        allowed_hosts="api.example.com",
        cors_allowed_origins="https://app.example.com",
        max_request_body_bytes=2_097_152,
        request_timeout_seconds=45,
        max_concurrent_requests=25,
        rate_limit_requests=30,
        rate_limit_window_seconds=15,
    )

    export_runtime_settings(settings)

    assert os.environ["LUNCHMONEY_TRUSTED_PROXY_IPS"] == "10.0.0.2"
    assert os.environ["LUNCHMONEY_ALLOWED_HOSTS"] == "api.example.com"
    assert os.environ["LUNCHMONEY_CORS_ALLOWED_ORIGINS"] == "https://app.example.com"
    assert os.environ["LUNCHMONEY_MAX_REQUEST_BODY_BYTES"] == "2097152"
    assert os.environ["LUNCHMONEY_REQUEST_TIMEOUT_SECONDS"] == "45.0"
    assert os.environ["LUNCHMONEY_MAX_CONCURRENT_REQUESTS"] == "25"
    assert os.environ["LUNCHMONEY_RATE_LIMIT_REQUESTS"] == "30"
    assert os.environ["LUNCHMONEY_RATE_LIMIT_WINDOW_SECONDS"] == "15"


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        (
            "trusted_proxy_ips",
            "proxy.internal",
            "does not appear to be an IPv4 or IPv6 address",
        ),
        ("allowed_hosts", "", "at least one host"),
        ("allowed_hosts", "*", "must not contain a wildcard"),
        ("cors_allowed_origins", "*", "must not contain a wildcard"),
    ],
)
def test_settings_reject_insecure_network_policy(
    field_name: str,
    value: str,
    error: str,
) -> None:
    """Reject wildcard and implicit network trust configuration."""
    with pytest.raises(ValueError, match=error):
        RuntimeSettings(**{field_name: value})


def test_mcp_runtime_forces_ephemeral_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent standalone MCP transport processes from opening persistent storage."""
    import lunchmoney_mcp.config as config_module

    monkeypatch.setenv("LUNCHMONEY_DATABASE_URL", "sqlite+aiosqlite:///persistent.db")
    monkeypatch.setattr(config_module, "_runtime_mode", None)
    configure_runtime_mode("mcp")

    assert resolve_database_url() == IN_MEMORY_DATABASE_URL


def test_stateless_settings_select_shared_memory_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve the shared in-memory URL when stateless mode is enabled."""
    monkeypatch.setenv("LUNCHMONEY_STATELESS", "true")
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    assert resolve_database_url() == IN_MEMORY_DATABASE_URL
    get_settings.cache_clear()


def test_database_url_overrides_stateless_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve explicit and environment database URL precedence in stateless mode."""
    environment_url = "sqlite+aiosqlite:///environment.db"
    explicit_url = "sqlite+aiosqlite:///explicit.db"
    monkeypatch.setenv("LUNCHMONEY_STATELESS", "true")
    monkeypatch.setenv("LUNCHMONEY_DATABASE_URL", environment_url)
    get_settings.cache_clear()

    assert resolve_database_url() == environment_url
    assert resolve_database_url(explicit_url) == explicit_url
    get_settings.cache_clear()


def test_dotenv_database_url_overrides_stateless_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Preserve a database URL supplied through Pydantic's `.env` source."""
    dotenv_url = "sqlite+aiosqlite:///dotenv.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LUNCHMONEY_STATELESS", "true")
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(f"LUNCHMONEY_DATABASE_URL={dotenv_url}\n")
    get_settings.cache_clear()

    assert resolve_database_url() == dotenv_url
    get_settings.cache_clear()


def test_dotenv_default_database_url_overrides_stateless_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Preserve an explicitly configured default URL over stateless mode."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LUNCHMONEY_STATELESS", "true")
    monkeypatch.delenv("LUNCHMONEY_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(f"LUNCHMONEY_DATABASE_URL={DEFAULT_DATABASE_URL}\n")
    get_settings.cache_clear()

    assert resolve_database_url() == DEFAULT_DATABASE_URL
    get_settings.cache_clear()


def test_get_settings_cached() -> None:
    """Return cached runtime and secret settings instances."""
    settings_1 = get_settings()
    settings_2 = get_settings()
    assert settings_1 is settings_2
    secret_settings_1 = get_secret_settings()
    secret_settings_2 = get_secret_settings()
    assert secret_settings_1 is secret_settings_2
