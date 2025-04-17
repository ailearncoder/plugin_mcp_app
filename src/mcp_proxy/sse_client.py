"""Create a local server that proxies requests to a remote server over SSE."""

from typing import Any

from mcp.client.session import ClientSession, RequestResponder
from mcp.client.sse import sse_client
from mcp.server.stdio import stdio_server
import mcp.types as types
import logging
import anyio.lowlevel

from .proxy_server import create_proxy_server

async def my_message_handler(
    message: RequestResponder[types.ServerRequest, types.ClientResult]
    | types.ServerNotification
    | Exception,
) -> None:
    logging.error(f"Received message: {message}, type: {type(message)} type: {isinstance(message, Exception)}")
    await anyio.lowlevel.checkpoint()
    if isinstance(message, Exception):
        raise message

async def callback(type: str, data: dict[str, Any]) -> None:
    logging.info(f"Received callback: {type}, data: {data}")


async def run_sse_client(url: str, headers: dict[str, Any] | None = None) -> None:
    """Run the SSE client.

    Args:
        url: The URL to connect to.
        headers: Headers for connecting to MCP server.

    """
    logging.info(f"Connecting to SSE endpoint: {url}")
    async with sse_client(url=url, headers=headers, sse_read_timeout=None) as streams, ClientSession(*streams, message_handler=my_message_handler) as session:
        app = await create_proxy_server(session, callback)
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
                raise_exceptions=False
            )
