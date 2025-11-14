from xiaozhi_app.plugins.android import AndroidDevice
from typing import Optional, Callable
from xiaozhi_app.core import MCPProxy
from importlib.resources import files
from .config_server import ConfigServer
from fastmcp import Client
import logging
import asyncio
import json
import argparse
import os

logging.basicConfig(level=logging.INFO)

def init_files(config_path: str):
    data_path = files('plugin_mcp_app').joinpath('assets')
    mcp_servers = data_path.joinpath('mcp_servers.json')
    if not os.path.exists(f"{config_path}/mcp_servers.json"):
        if not os.path.exists(config_path):
            os.makedirs(config_path)
            logging.info(f"Create config path success: {config_path}")
        cur_mcp_servers = json.loads(mcp_servers.read_text())
    else:
        logging.info(f"mcp_servers.json already exists: {config_path}")
        with open(f"{config_path}/mcp_servers.json", "r") as f:
            cur_mcp_servers = json.load(f)
        cur_mcp_servers["mcpServers"].update(json.loads(mcp_servers.read_text())["mcpServers"])
    for item in cur_mcp_servers["mcpServers"].values():
        if "env" in item and "HOME_ASSISTANT_CACHE_DIR" in item["env"]:
            item["env"]["HOME_ASSISTANT_CACHE_DIR"] = os.path.join(config_path, ".cache")
    with open(f"{config_path}/mcp_servers.json", "w") as f:
        json.dump(cur_mcp_servers, f)
    """初始化证书文件，将自定义 PEM 证书添加到 certifi CA 包中"""
    try:
        # 获取 PEM 文件路径
        pem_file_path = data_path.joinpath('ZeroSSL_ECC_Domain_Secure_Site_CA.pem')

        # 验证 PEM 文件是否存在
        if not pem_file_path.is_file():
            logging.warning(f"PEM 证书文件不存在: {pem_file_path}")
            return

        # 获取 certifi CA 文件路径（使用更健壮的方式）
        try:
            import certifi
            ca_file_path = certifi.where()
        except ImportError:
            logging.error("certifi 模块未安装，无法获取 CA 证书路径")
            return

        # 验证 CA 文件是否存在
        if not os.path.isfile(ca_file_path):
            logging.error(f"CA 证书文件不存在: {ca_file_path}")
            return

        # 读取 PEM 文件内容
        try:
            pem_content = pem_file_path.read_text(encoding='utf-8')
            if not pem_content.strip():
                logging.warning("PEM 证书文件为空")
                return
        except Exception as e:
            logging.error(f"读取 PEM 文件失败 {pem_file_path}: {e}")
            return

        # 检查证书是否已存在于 CA 文件中
        ca_content = ''
        try:
            with open(ca_file_path, 'r', encoding='utf-8') as f:
                ca_content = f.read()
                if pem_content.strip() in ca_content:
                    logging.info(f"PEM 证书已存在于 CA 文件中，跳过添加: {ca_file_path}")
                    return
        except Exception as e:
            logging.error(f"读取 CA 文件失败 {ca_file_path}: {e}")
            return

        # 追加 PEM 证书到 CA 文件
        try:
            with open(ca_file_path, 'a', encoding='utf-8') as f:
                # 确保前面有换行符分隔
                if not ca_content.endswith('\n'):
                    f.write('\n')
                f.write(pem_content)
                if not pem_content.endswith('\n'):
                    f.write('\n')
            logging.info(f"成功添加 PEM 证书到 CA 文件: {ca_file_path}")
        except PermissionError:
            logging.error(f"没有权限写入 CA 文件: {ca_file_path}。可能需要管理员权限")
        except Exception as e:
            logging.error(f"写入 CA 文件失败 {ca_file_path}: {e}")

    except Exception as e:
        logging.error(f"初始化证书文件时发生未知错误: {e}")

class ClientTool:
    def __init__(self, client: Client, loop: asyncio.AbstractEventLoop, config_dir: str, restart_callback: Callable[[], None]):
        self.client: Client = client
        self.loop: asyncio.AbstractEventLoop = loop
        self.server = ConfigServer(
            config_dir=config_dir,
            port=0,  # 可以指定端口或使用 0 自动分配
            on_config_update=self.on_update
        )
        # Callback to signal the main manager to restart the client
        self.restart_callback = restart_callback

    async def _deal_server(self, arguments: dict) -> str:
        try:
            is_running = self.server.is_running()
            action = arguments.get("action", "")
            message = "success"
            data = {}
            if action == "start":
                if not is_running:
                    data["url"] = await self.server.start()
                else:
                    message = "already running"
            elif action == "stop":
                if is_running:
                    await self.server.stop()
                else:
                    message = "already stopped"
            elif action == "status":
                data["is_running"] = is_running
                if is_running:
                    data["url"] = self.server.get_server_url()
            return json.dumps({"code": 0, "message": message, "data": data}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"code": -1, "message": str(e)}, ensure_ascii=False)

    async def invoke_tool(self, name: str, arguments: dict) -> str:
        try:
            logging.info(f"invoke tool: {name} start, arguments: {arguments}")
            mcp_arguments = {}
            for key, value in arguments.items():
                mcp_arguments[key] = value["value"]
            logging.info(f"invoke tool: {name} arguments: {mcp_arguments}")
            if name == "plugin-mcp-app-config-server":
                return await self._deal_server(mcp_arguments)
            result = await self.client.call_tool(name, mcp_arguments, timeout=30)
            logging.info(f"invoke tool: {name} end, arguments: {arguments}, result: {result.structured_content}")
            content = ""
            if result.structured_content:
                nextTools = result.structured_content.get("nextTools", [])
                if len(nextTools) > 0:
                    success = result.structured_content.get("success", False)
                    if success:
                        result = result.structured_content.get("result", {})
                        return self.invoke_global_tool(nextTools[0], result)
                content = json.dumps(result.structured_content, ensure_ascii=False)
            else:
                content_list = [item.model_dump() for item in result.content]
                content = json.dumps(content_list, ensure_ascii=False)
            logging.info(f"invoke tool name: {name} arguments: {arguments} result: {content}")
            return content
        except Exception as e:
            logging.error(f"invoke tool name: {name} arguments: {arguments} error: {e}")
            return json.dumps({"error": str(e)})

    def invoke_tool_sync(self, name: str, arguments: dict) -> str:
        """同步调用工具，通过在现有事件循环中调度异步任务"""
        future = asyncio.run_coroutine_threadsafe(
            self.invoke_tool(name, arguments),
            self.loop
        )
        return future.result(timeout=35)  # 稍微大于invoke_tool中的timeout

    async def on_update(self, config_data):
        """配置更新回调示例, now triggers a client restart."""
        logging.info(f"配置已更新: {config_data}, 正在触发客户端重启...")
        if self.restart_callback:
            self.restart_callback()

    def update_server_status(self, server_name: str, status: str, error: Optional[str] = None):
        if self.server.is_running():
            self.server.update_server_status(server_name, status, error)

    def invoke_global_tool(self, name: str, arguments: dict) -> str:
        dealed_arguments = {}
        if name.startswith("self."):
            for key, value in arguments.items():
                if isinstance(value, str) or isinstance(value, float) or isinstance(value, bool) or isinstance(value, int):
                    dealed_arguments[key] = value
                else:
                    dealed_arguments[key] = json.dumps(value, ensure_ascii=False)
        else:
            dealed_arguments = arguments
        device = AndroidDevice()
        rpc_object = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": dealed_arguments,
            },
        }
        logging.info(f"invoke global tool name: {name}, arguments: {arguments}")
        success, data, error = device.call_method_android("callMcp", json.dumps(rpc_object), 5000)
        logging.info(f"invoke global tool name: {name} result success: {success}, data: {data}, error: {error}")
        return json.dumps({"success": success, "data": data, "error": error}, ensure_ascii=False)

class ClientManager:
    """Manages the lifecycle of the MCP client and its tools."""
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.mcp_proxy = MCPProxy()
        self.loop = asyncio.get_running_loop()
        self._restart_required = asyncio.Event()

    def trigger_restart(self):
        """Sets the event to signal that a restart is required."""
        self._restart_required.set()

    async def run(self):
        """Main application loop that handles client connection and restarts."""
        if not self.mcp_proxy.connect():
            logging.error("connect to mcp failed")
            return

        while True:
            self._restart_required.clear()

            try:
                with open(f"{self.config_path}/mcp_servers.json") as f:
                    config = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load config file: {e}. Retrying in 15 seconds.")
                await asyncio.sleep(15)
                continue

            servers = {key: False for key in config.get("mcpServers", {})}
            logging.info(f"Attempting to connect client with servers: {list(servers.keys())}")

            client = Client(config)

            try:
                async with client:
                    client_tool = ClientTool(client, self.loop, self.config_path, self.trigger_restart)
                    self.mcp_proxy.call_mcp_tool = client_tool.invoke_tool_sync

                    await client.ping()
                    logging.info("Client connected successfully. Entering operational loop.")

                    # This inner loop runs as long as the client is connected and no restart is requested.
                    while not self._restart_required.is_set():
                        try:
                            discovered_tools = []
                            tools = await client.list_tools()

                            # Reset server readiness flags for this check
                            for key in servers: servers[key] = False

                            for tool in tools:
                                if len(servers) > 1:
                                    try:
                                        title, name = tool.name.split("_", maxsplit=1)
                                        if title in servers:
                                            servers[title] = True
                                    except ValueError:
                                        logging.warning(f"Could not parse server title from tool name: {tool.name}")
                                discovered_tools.append(tool.model_dump())

                            self.mcp_proxy.set_tools(discovered_tools)

                            all_servers_ready = all(servers.values())
                            if not all_servers_ready and len(servers) > 1:
                                for k, v in servers.items():
                                    if not v:
                                        logging.info(f"Server '{k}' is not ready yet.")

                            logging.info("Client operational. Checking for updates...")
                            for item in servers.keys():
                                client_tool.update_server_status(item, "running")

                            # Wait for the restart signal, with a timeout to allow periodic work.
                            logging.info("plugin-mcp-app start success")
                            await asyncio.wait_for(self._restart_required.wait(), timeout=300)

                        except asyncio.TimeoutError:
                            # This is the normal operational path, loop continues.
                            continue
                        except Exception as e:
                            logging.error(f"Error in operational loop: {e}. Forcing reconnect.")
                            # Break inner loop to trigger a reconnect.
                            break

            except Exception as e:
                logging.error(f"Client connection failed or was lost: {e}. Retrying in 10 seconds.")
                await asyncio.sleep(10)

            if self._restart_required.is_set():
                logging.info("Restarting client due to configuration update...")
            else:
                logging.warning("Client loop exited unexpectedly. Reconnecting...")

            await asyncio.sleep(1) # Brief pause before restarting the main loop.

async def main_client():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--config_dir", help="Configuration file directory", default="config")
    args = argparser.parse_args()
    config_path = args.config_dir

    init_files(config_path)

    manager = ClientManager(config_path)
    await manager.run()

def main():
    try:
        asyncio.run(main_client())
    except KeyboardInterrupt:
        logging.info("Application shutting down.")
