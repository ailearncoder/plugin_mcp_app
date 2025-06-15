from xiaozhi_app.core import Thing
from xiaozhi_app.plugins import AndroidDevice
from typing import Tuple
import mcp_hub
import asyncio
import logging
import time
import sys
import os
import json

def run_mcp_pipe(endpoint: str, servers_num: int = 0):
    print(f"Starting mcp_pipe.sh with endpoint: {endpoint}, servers_num: {servers_num}")
    mcphub_host = os.getenv("THING_HOST", "127.0.0.1")
    mcphub_port = os.getenv("MCP_HUB_PORT", "3000")
    with open('src/mcp.json', 'r') as f:
        mcp_config = json.load(f)
    mcp_config["mcps"][0]["params"]["url"] = f"http://{mcphub_host}:{mcphub_port}/mcp"
    mcp_config["mcps"][0]["enable"] = servers_num > 0
    mcp_config["mcps"][1]["params"]["url"] = endpoint
    mcp_config["mcps"][1]["enable"] = len(endpoint) > 0
    with open('src/mcp.json', 'w') as f:
        json.dump(mcp_config, f, ensure_ascii=False, indent=4)
    os.system("sh ./src/mcp_proxy.sh &")

async def check_mcp_servers():
    servers_num = 0
    run_mcp_pipe(mcp_thing._mcp_url_mcp, servers_num)
    while True:
        try:
            servers = mcp_hub.get_servers()
            cur_servers = [server for server in servers["data"] if server['enabled'] and server["status"] == "connected"]
            if len(cur_servers) == servers_num:
                await asyncio.sleep(5)
                continue
            servers_num = len(cur_servers)
            print(f"Found {servers_num} servers")
            run_mcp_pipe(mcp_thing._mcp_url_mcp, servers_num)
            await asyncio.sleep(1)
        except Exception as e:
            if servers_num != 0:
                servers_num = 0
                print(f"Found {servers_num} servers")
                run_mcp_pipe(mcp_thing._mcp_url_mcp, servers_num)
            print(f"Error getting servers: {e}")
            await asyncio.sleep(5)

# def check_mcp_servers_thread():
#     thread = threading.Thread(target=check_mcp_servers)
#     thread.daemon = True
#     thread.start()

class McpProxy(Thing):
    def __init__(self):
        self._online = True
        self._device = AndroidDevice()
        self._mcp_url_mcp = None
        self._mcp_url_sse = None
        super().__init__()

    def setEnabled(self, enabled) -> Tuple[bool, str]:
        print(f"Setting enabled to {enabled}")
        return super().setEnabled(enabled)

    def config_mcp_url_mcp(self, mcp_url_mcp: str):
        self._mcp_url_mcp = mcp_url_mcp
        print(f"Configuring mcp_url_mcp to {mcp_url_mcp}")
        return True

    def config_mcp_url_sse(self, mcp_url_sse: str):
        self._mcp_url_sse = mcp_url_sse
        print(f"Configuring mcp_url_sse to {mcp_url_sse}")
        return True

    def SaveConfig(self):
        print(f"Saving config: {self._mcp_url_mcp}")
        run_mcp_pipe(self._mcp_url_mcp)

async def check_connection(mcp_thing: McpProxy):
    try:
        while mcp_thing.connected:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        mcp_thing.disconnect()
    exit(0)

async def main(mcp_thing: McpProxy):
    task1 = asyncio.create_task(check_connection(mcp_thing))
    task2 = asyncio.create_task(check_mcp_servers())
    await asyncio.gather(task1, task2)

# Usage
if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', force=True)
    mcp_thing = McpProxy()
    if len(sys.argv) > 1 and sys.argv[1] == "info":
        # 这个不能去掉，否则无法识别插件信息
        with open("info.json", "w") as f:
            f.write(mcp_thing.get_definition())
        exit(0)
    mcp_thing.connect()
    asyncio.run(main(mcp_thing))
