"""API-key protection for the REST application."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from lunchmoney_mcp.config import (
    RuntimeSettings,
    SecretSettings,
    get_secret_settings,
    get_settings,
)

if TYPE_CHECKING:
    from fastmcp.server.auth import AuthProvider


def _oidc_proxy_class() -> type[Any]:
    """Load FastMCP's optional OIDC proxy only when OAuth is configured."""
    from fastmcp.server.auth import OIDCProxy

    return OIDCProxy


def get_mcp_oauth_provider(
    settings: RuntimeSettings | None = None,
    secret_settings: SecretSettings | None = None,
) -> AuthProvider | None:
    """Build the optional OIDC proxy that protects remote MCP transports.

    Parameters
    ----------
    settings : RuntimeSettings | None
        Explicit settings for construction or the cached application settings.
    secret_settings : SecretSettings | None
        Explicit secret settings for construction or the cached secret settings.

    Returns
    -------
    AuthProvider | None
        An OAuth provider when all required OIDC settings are configured, otherwise
        ``None`` so local MCP use remains unauthenticated.

    Raises
    ------
    ValueError
        If only part of the required OAuth configuration is supplied.
    """
    resolved_settings = settings or get_settings()
    resolved_secret_settings = secret_settings or get_secret_settings()
    configuration = {
        "LUNCHMONEY_MCP_OAUTH_CONFIG_URL": (resolved_settings.mcp_oauth_config_url),
        "LUNCHMONEY_MCP_OAUTH_CLIENT_ID": (resolved_settings.mcp_oauth_client_id),
        "LUNCHMONEY_MCP_OAUTH_BASE_URL": resolved_settings.mcp_oauth_base_url,
    }
    if not any(configuration.values()):
        return None

    missing = [name for name, value in configuration.items() if value is None]
    if missing:
        raise ValueError(
            "OAuth requires "
            + ", ".join(missing)
            + " when any OAuth setting is configured"
        )

    return _oidc_proxy_class()(
        config_url=resolved_settings.mcp_oauth_config_url,
        client_id=resolved_settings.mcp_oauth_client_id,
        client_secret=resolved_secret_settings.mcp_oauth_client_secret,
        audience=resolved_settings.mcp_oauth_audience,
        base_url=resolved_settings.mcp_oauth_base_url,
    )


async def verify_api_key(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Require the configured API key for REST requests when one is configured.

    Parameters
    ----------
    request : Request
        Incoming REST request whose ``X-API-Key`` header is checked.
    call_next : Callable[[Request], Awaitable[Response]]
        ASGI continuation used for authorized requests.

    Returns
    -------
    Response
        The downstream response, or a 401 response for missing or invalid keys.
    """
    if request.url.path.startswith(("/mcp", "/static/")) or request.url.path in {
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
    }:
        return await call_next(request)

    expected_key = get_secret_settings().mcp_api_key
    provided_key = request.headers.get("X-API-Key")
    if request.url.path == "/metrics" and expected_key is None:
        return JSONResponse(
            status_code=403,
            content={"detail": "Metrics endpoint requires API key configuration"},
        )
    if expected_key is not None and not secrets.compare_digest(
        provided_key or "", expected_key
    ):
        return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
    return await call_next(request)


__all__ = ["get_mcp_oauth_provider", "verify_api_key"]
