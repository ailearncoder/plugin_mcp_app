from xiaozhi_app.core import Thing
from xiaozhi_app.plugins import AndroidDevice
from typing import Tuple
import mcp_hub
import asyncio
import logging
import time
import sys
import os

def run_mcp_pipe(endpoint: str):
    print(f"Starting mcp_pipe.sh with endpoint: {endpoint}")
    if endpoint == "":
        print("Endpoint is empty, skipping mcp_pipe.sh")
        return
    os.environ['MCP_ENDPOINT'] = endpoint
    os.system("sh ./src/mcp_pipe.sh &")

# def run_mcp_pipe_thread(endpoint: str):
#     print(f"Starting mcp_pipe.sh with endpoint: {endpoint}")
#     thread = threading.Thread(target=run_mcp_pipe, args=(endpoint,))
#     thread.daemon = True
#     thread.start()

async def check_mcp_servers():
    servers_num = 0
    while True:
        try:
            servers = mcp_hub.get_servers()
            cur_servers = [server for server in servers["data"] if server['enabled'] and server["status"] == "connected"]
            if len(cur_servers) == servers_num:
                await asyncio.sleep(5)
                continue
            servers_num = len(cur_servers)
            print(f"Found {servers_num} servers")
            run_mcp_pipe(mcp_thing._mcp_url)
            await asyncio.sleep(1)
        except Exception as e:
            servers_num = 0
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
        self._mcp_url = None
        super().__init__()

    def setEnabled(self, enabled) -> Tuple[bool, str]:
        print(f"Setting enabled to {enabled}")
        return super().setEnabled(enabled)

    def config_mcp_url(self, mcp_url: str):
        self._mcp_url = mcp_url
        print(f"Configuring mcp_url to {mcp_url}")
        return True

    def SaveConfig(self):
        print(f"Saving config: {self._mcp_url}")
        run_mcp_pipe(self._mcp_url)

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
