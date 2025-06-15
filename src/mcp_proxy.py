import os
import sys
import fcntl
import json
import signal
import asyncio
import logging
import time
from typing import Callable, Awaitable, Any, Dict, List, Tuple, Optional
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from mcp.client.streamable_http import streamablehttp_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp import ClientSession

# Assuming MCPProxy is defined elsewhere, e.g.:
from xiaozhi_app.core import MCPProxy

# --- Constants ---
DEFAULT_STREAMABLE_URL = "https://mcphub.mac.axyz.cc:30923/mcp/ee770364-0146-4a8d-9c4f-922a2652ea8e"
DEFAULT_SSE_URL = "https://mcphub.mac.axyz.cc:30923/sse/ee770364-0146-4a8d-9c4f-922a2652ea8e"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MCPServiceManager:
    """
    Manages connections to MCP services, tool discovery, and tool invocation.
    """

    def __init__(self, config_path: str = "mcp.json"):
        self.mcp_configs: List[Dict] = self._load_config(config_path)
        self.mcp_tool_map: Dict[str, Dict[str, Any]] = {}
        self._client_factories = {
            "streamable": self._get_streamable_client_streams,
            "stdio": self._get_stdio_client_streams,
            "sse": self._get_sse_client_streams,
        }

    def _load_config(self, config_path: str) -> List[Dict]:
        """Loads and filters MCP configurations."""
        try:
            with open(config_path) as f:
                config = json.load(f)
            # Filter for enabled MCPs
            enabled_mcps = [mcp for mcp in config.get("mcps", []) if mcp.get("enable")]
            logging.info(f"Loaded {len(enabled_mcps)} enabled MCP configurations from {config_path}")
            return enabled_mcps
        except FileNotFoundError:
            logging.error(f"Configuration file {config_path} not found.")
            return []
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {config_path}.")
            return []

    def _get_streamable_client_streams(
        self, params: Dict
    ) -> Tuple[MemoryObjectReceiveStream, MemoryObjectSendStream, Any]:
        url = params.get("url", DEFAULT_STREAMABLE_URL)
        headers = params.get("headers")
        return streamablehttp_client(url=url, headers=headers)

    def _get_stdio_client_streams(
        self, params: Dict
    ) -> Tuple[MemoryObjectReceiveStream, MemoryObjectSendStream]:
        server_params = StdioServerParameters(
            command=params["command"],
            args=params["args"],
            env=params.get("env"),
            cwd=params.get("cwd"),
        )
        return stdio_client(server=server_params)

    def _get_sse_client_streams(
        self, params: Dict
    ) -> Tuple[MemoryObjectReceiveStream, MemoryObjectSendStream]:
        url = params.get("url", DEFAULT_SSE_URL)
        headers = params.get("headers")
        # sse_client returns (read_stream, write_stream)
        # We need to match the tuple size of streamablehttp_client for unpacking if we want a generic unpack
        # However, the original code for streamablehttp_client used `_` for the third element.
        # Let's stick to what each client returns and handle it.
        return sse_client(url=url, headers=headers)

    async def _execute_action_with_client(
        self,
        mcp_type: str,
        mcp_params: Dict,
        action: Callable[[ClientSession], Awaitable[Any]],
    ) -> Any:
        """
        Generic helper to connect to an MCP client and execute an action.
        """
        client_factory = self._client_factories.get(mcp_type)
        if not client_factory:
            raise ValueError(f"Unsupported MCP type: {mcp_type}")

        # The context managers for clients return different numbers of values.
        # streamablehttp_client returns 3, stdio_client and sse_client return 2.
        # We need to handle this unpacking carefully.

        if mcp_type == "streamable":
            async with client_factory(mcp_params) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await action(session)
        elif mcp_type in ["stdio", "sse"]:
             async with client_factory(mcp_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await action(session)
        else: # Should not happen due to earlier check, but good for completeness
            raise ValueError(f"Client factory for {mcp_type} not correctly handled for stream unpacking.")

    async def _list_tools_for_mcp(self, mcp_entry: Dict) -> List[Dict]:
        """Lists tools for a single MCP configuration."""
        mcp_type = mcp_entry["type"]
        mcp_params = mcp_entry["params"]

        async def list_tools_action(session: ClientSession) -> List[Dict]:
            logging.info(f"Listing tools for MCP type '{mcp_type}' with params: {mcp_params}")
            tools_response = await session.list_tools()
            formatted_tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in tools_response.tools
            ]
            logging.info(f"Found {len(formatted_tools)} tools for MCP type '{mcp_type}'")
            return formatted_tools

        try:
            return await self._execute_action_with_client(
                mcp_type, mcp_params, list_tools_action
            )
        except Exception as e:
            logging.error(f"Error listing tools for MCP {mcp_type} ({mcp_params.get('url', mcp_params.get('command'))}): {e}", exc_info = e)
            return []

    async def _call_tool_for_mcp(
        self, mcp_entry: Dict, tool_name: str, arguments: Dict
    ) -> str:
        """Calls a specific tool on a specific MCP."""
        mcp_type = mcp_entry["type"]
        mcp_params = mcp_entry["params"]

        async def call_tool_action(session: ClientSession) -> str:
            logging.info(f"Calling tool '{tool_name}' on MCP type '{mcp_type}' with args: {arguments}")
            result = await session.call_tool(tool_name, arguments)
            # Assuming result.content is a list and has at least one item with a 'text' attribute
            if result.content and hasattr(result.content[0], 'text'):
                return result.content[0].text
            logging.warning(f"Tool '{tool_name}' on MCP '{mcp_type}' returned unexpected content structure.")
            return json.dumps({"error": "Unexpected tool result format"})

        return await self._execute_action_with_client(
            mcp_type, mcp_params, call_tool_action
        )

    async def discover_all_tools(self) -> List[Dict]:
        """Discovers tools from all configured MCPs and populates the tool map."""
        all_tools_list = []
        self.mcp_tool_map.clear() # Clear previous map if called multiple times

        for mcp_entry in self.mcp_configs:
            tools = await self._list_tools_for_mcp(mcp_entry)
            all_tools_list.extend(tools)
            for tool_info in tools:
                tool_name = tool_info["name"]
                if tool_name in self.mcp_tool_map:
                    logging.warning(
                        f"Tool '{tool_name}' from MCP type '{mcp_entry['type']}' "
                        f"is already mapped. Overwriting is not standard; check config. "
                        f"Original: {self.mcp_tool_map[tool_name]['tool_info']['name']} "
                        f"type: {self.mcp_tool_map[tool_name]['mcp_config']['type']}"
                    )
                    # Decide on a strategy: overwrite, skip, or error.
                    # For now, let's allow overwrite but log a strong warning.
                self.mcp_tool_map[tool_name] = {"tool_info": tool_info, "mcp_config": mcp_entry}
                logging.info(f"Mapped tool '{tool_name}' to MCP type '{mcp_entry['type']}'")
        logging.info(f"Total tools discovered and mapped: {len(self.mcp_tool_map)}")
        return all_tools_list

    async def invoke_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Invokes a tool by its name using the mapped MCP configuration.
        The 'arguments' dict is expected to be in the format:
        {"param_name1": {"value": "actual_value1"}, "param_name2": {"value": "actual_value2"}}
        This will be converted to {"param_name1": "actual_value1", ...} before calling the tool.
        """
        if tool_name not in self.mcp_tool_map:
            logging.warning(f"Tool '{tool_name}' not found in mapped tools.")
            return json.dumps(
                {"success": False, "message": f"Tool '{tool_name}' not found"}
            )

        tool_registration = self.mcp_tool_map[tool_name]
        mcp_entry = tool_registration["mcp_config"]

        try:
            # Convert arguments from {"param": {"value": val}} to {"param": val}
            # This matches the original code's expectation.
            processed_args = {key: value["value"] for key, value in arguments.items() if isinstance(value, dict) and "value" in value}
            if len(processed_args) != len(arguments):
                logging.warning(f"Some arguments for tool '{tool_name}' were not in the expected format {{'value': ...}} and were skipped.")

            logging.info(f"Invoking tool '{tool_name}' via MCP '{mcp_entry['type']}' with processed args: {processed_args}")
            message = await self._call_tool_for_mcp(
                mcp_entry, tool_name, processed_args
            )
            logging.info(f"Successfully invoked tool '{tool_name}'. Result: {message[:100]}...") # Log snippet
            return json.dumps({"success": True, "message": message})
        except Exception as e:
            logging.error(f"Error invoking tool '{tool_name}': {e}", exc_info=True)
            return json.dumps(
                {"success": False, "message": f"Error calling tool '{tool_name}': {e}"}
            )

    def invoke_tool_sync(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Synchronous version of invoke_tool. This method should be used when the calling context
        is not async (e.g., in a non-async function).
        """
        return asyncio.run(self.invoke_tool(tool_name, arguments))

async def main_proxy_loop(config_file: str = "mcp.json"):
    """
    Main application loop to set up and run the MCP proxy.
    """
    proxy = MCPProxy() # Your actual proxy instance
    manager = MCPServiceManager(config_path=config_file)

    # Discover tools and prepare them for the proxy
    # This needs to be done before connecting or setting handlers if tools are needed at connect time
    discovered_tools = await manager.discover_all_tools()

    # Set up the proxy
    proxy.connect()
    proxy.call_mcp_tool = manager.invoke_tool_sync # Assign the async method
    proxy.set_tools(discovered_tools) # Pass the list of tool dicts

    logging.info("MCP Proxy is running. Press Ctrl+C to stop.")
    try:
        while proxy.connected:
            # In a real scenario, the proxy would have its own event loop
            # or mechanism for receiving requests. This sleep is just a placeholder.
            # For example, if proxy.process_incoming_request was how it worked:
            # await proxy.process_incoming_request("some_tool_name", {"arg1": {"value": "test"}})
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        logging.info("MCP Proxy shutting down...")
    finally:
        proxy.disconnect()
        logging.info("MCP Proxy stopped.")

def single_instance():
    lock_file = 'mcp_proxy.lock'
    try:
        lock_fd = os.open(lock_file, os.O_WRONLY | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # 读取锁文件中的旧PID
        try:
            with open(lock_file, 'r') as f:
                old_pid = int(f.read())
        except:
            old_pid = None
        # 尝试终止旧进程
        if old_pid:
            try:
                os.kill(old_pid, signal.SIGTERM)
                print(f"Terminated old instance (PID: {old_pid})")
                time.sleep(0.1)
            except ProcessLookupError:
                pass
        # 再次尝试获取锁
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            print("Failed to terminate old instance", file=sys.stderr)
            sys.exit(1)
    # 将当前PID写入锁文件
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    return lock_fd

if __name__ == "__main__":
    lock_fd = single_instance()
    dummy_mcp_config_path = "mcp.json"
    try:
        with open(dummy_mcp_config_path, "r") as f:
            json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Creating a dummy '{dummy_mcp_config_path}' for demonstration.")
        dummy_config_content = {
            "mcps": [
                {
                    "type": "streamable", # or "stdio" or "sse"
                    "enable": False, # Set to True to test, but will fail without a server
                    "params": {
                        "url": "http://localhost:8000/mcp_endpoint", # Example
                        # For stdio:
                        # "command": "python",
                        # "args": ["my_mcp_server_script.py"],
                        # "cwd": "/path/to/script/dir"
                    }
                }
            ]
        }
        with open(dummy_mcp_config_path, "w") as f:
            json.dump(dummy_config_content, f, indent=2)

    asyncio.run(main_proxy_loop(config_file=dummy_mcp_config_path))
