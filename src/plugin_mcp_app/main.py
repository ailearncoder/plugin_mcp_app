
from xiaozhi_app.core import MCPProxy
from importlib.resources import files
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
        os.makedirs(config_path)
        logging.info(f"Create config path success: ${config_path}")
        with open(f"{config_path}/mcp_servers.json", "w") as f:
            f.write(mcp_servers.read_text())
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
    def __init__(self, client: Client, loop: asyncio.AbstractEventLoop):
        self.client: Client = client
        self.loop: asyncio.AbstractEventLoop = loop

    async def invoke_tool(self, name: str, arguments: dict) -> str:
        try:
            logging.info(f"invoke tool: {name} start, arguments: {arguments}")
            mcp_arguments = {}
            for key, value in arguments.items():
                mcp_arguments[key] = value["value"]
            logging.info(f"invoke tool: {name} arguments: {mcp_arguments}")
            result = await self.client.call_tool(name, mcp_arguments, timeout=30)
            logging.info(f"invoke tool: {name} end, arguments: {arguments}")
            content = ""
            if result.structured_content:
                content = json.dumps(result.structured_content, ensure_ascii=False)
            else:
                content_list = []
                for item in result.content:
                    content_list.append(item.model_dump())
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


async def main_client():
    # --config_dir config_path
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--config_dir", help="Configuration file directory", default="config")
    args = argparser.parse_args()
    config_path = args.config_dir
    init_files(config_path)
    with open(f"{config_path}/mcp_servers.json") as f:
        config: dict = json.load(f)
    servers = {key: False for key in config["mcpServers"]}
    logging.info(f"local servers: {servers}")
    client: Client = Client(config)
    mcpProxy = MCPProxy()
    if not mcpProxy.connect():
        logging.error("connect to mcp failed")
        return
    
    loop = asyncio.get_running_loop()
    
    async with client:
        clientTool = ClientTool(client, loop)
        # Basic server interaction
        await client.ping()
        mcpProxy.call_mcp_tool = clientTool.invoke_tool_sync  # Assign the async method
        # List available operations
        while True:
            discovered_tools = []
            tools = await client.list_tools()
            for tool in tools:
                if len(servers) > 1:
                    title, name = tool.name.split("_", maxsplit=1)
                    logging.info(f"tool: {title} {name}")
                    servers[title] = True
                logging.info(f"tool: {tool.name}")
                discovered_tools.append(tool.model_dump())
            mcpProxy.set_tools(discovered_tools)  # Pass the list of tool dicts
            if len(servers) > 1:
                for k, v in servers.items():
                    if not v:
                        logging.info(f"{k} is not ready")
                        await asyncio.sleep(1)
                        continue
            await asyncio.sleep(300)

def main():
    asyncio.run(main_client())
