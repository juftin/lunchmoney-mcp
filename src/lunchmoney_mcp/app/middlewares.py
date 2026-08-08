from typing import Awaitable, Callable

from fastapi.requests import Request
from fastapi.responses import HTMLResponse, Response


async def mcp_ui(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response | HTMLResponse:
    """Display the MCP Browser U.I"""
    if request.url.path in ["/mcp", "/mcp/"] and request.method == "GET":
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header:
            return HTMLResponse(
                content="""
            <!DOCTYPE html>
            <html>
                <head>
                    <title>MCP Server Endpoint</title>
                    <style>
                        body { font-family: system-ui, sans-serif; padding: 2rem; background: #f4f4f5; color: #18181b; }
                        .card { max-width: 600px; margin: 0 auto; background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
                        code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #0f172a; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h1>MCP Endpoint Active</h1>
                        <p>This endpoint serves Model Context Protocol traffic.</p>
                        <p>Connect your MCP client to: <code>/mcp</code></p>
                    </div>
                </body>
            </html>
            """
            )
    return await call_next(request)
