"""Create a local server that proxies requests to a remote server over SSE."""

from typing import Any

from mcp.client.session import ClientSession, RequestResponder
from xiaozhi_app.plugins import AndroidDevice
from mcp.client.sse import sse_client
from mcp.server.stdio import stdio_server
import mcp.types as types
import logging
import anyio.lowlevel
import anyio

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

# 创建一个任务队列
send_message_queue = anyio.create_memory_object_stream()
async def process_send_message_tasks():
    logging.info("Starting send_message task processing")
    async with send_message_queue[1]:
        async for message in send_message_queue[1]:
            try:
                device = AndroidDevice()
                device.set_message_loading(message)
            except Exception as e:
                logging.error(f"Error processing send_message: {e}")

def send_message(message: str) -> None:
    # 将消息放入队列
    send_message_queue[0].send_nowait(message)

async def callback(type: str, data: dict[str, Any]) -> None:
    logging.info(f"Received callback: {type}, data: {data}")
    action = data.get("action")
    tool_name = data.get("tool")
    try:
        if action == "begin":
            send_message(f"开始调用工具🔧：{tool_name}")
        elif action == "end":
            send_message(f"工具调用完成✅：{tool_name}")
    except Exception as e:
        logging.error(f"Error processing callback: {e}", exc_info=True)

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
