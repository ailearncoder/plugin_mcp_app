# MCP App Plugin

This project is a plugin designed to act as a universal proxy for various MCP (Meta-level Control Protocol) services. It allows a host application (like `xiaozhi_app`) to discover and utilize tools from different backends, including HTTP, stdio, and Server-Sent Events (SSE).

The plugin dynamically discovers available MCP servers from a central hub, updates its configuration, and exposes the aggregated tools from all connected services to the host application.

## Features

- **Dynamic Configuration**: Automatically discovers and connects to available MCP servers from an MCP Hub.
- **Multi-Backend Support**: Supports multiple MCP backend types:
    - `streamable`: For streamable HTTP-based services.
    - `stdio`: For command-line tools that communicate over standard I/O.
    - `sse`: For services that push data using Server-Sent Events.
- **Automatic Tool Discovery**: Introspects connected services to find available tools and their schemas.
- **Robust Process Management**: Ensures that the core proxy service is always running using a watchdog script.
- **Singleton Instance**: Guarantees that only one instance of the proxy is running at any given time.

## How It Works

The plugin consists of several key components that work together:

1.  **`main.py` (Plugin Entry Point)**:
    - This is the main interface with the host `xiaozhi_app`.
    - It periodically polls an MCP Hub (using `mcp_hub.py`) to get a list of active and connected MCP servers.
    - When the list of servers changes, it dynamically updates the `src/mcp.json` configuration file.
    - It then launches the `mcp_proxy.sh` script to start or restart the core proxy service with the new configuration.

2.  **`mcp_proxy.py` (Core Proxy Service)**:
    - This is the heart of the plugin. The `MCPServiceManager` class reads the `src/mcp.json` configuration.
    - It establishes connections to all enabled MCP services based on their type (`streamable`, `stdio`, `sse`).
    - It calls the `list_tools` method on each service to discover all available tools.
    - It maps each discovered tool to its corresponding MCP service, ready to be invoked.
    - It exposes an `invoke_tool` method that the host application can call. When called, it forwards the request to the correct backend service.

3.  **`mcp_proxy_run.py` & `mcp_proxy.sh` (Process Supervisor)**:
    - To ensure the proxy is always available, `mcp_proxy_run.py` runs in a loop, continuously starting `mcp_proxy.py`. If the main proxy script crashes, this watchdog script will automatically restart it.
    - `mcp_proxy.sh` is a simple shell script to launch the supervisor using `uv run`.
    - Both scripts use file-based locking (`.lock` files) to ensure only a single instance is active.

## Configuration

The behavior of the MCP proxy is controlled by `src/mcp.json`. This file is typically managed dynamically by `main.py` but can also be configured manually.

It contains a list of MCP services to connect to.

**Example `mcp.json`:**

```json
{
    "mcps": [
        {
            "type": "streamable",
            "params": {
                "url": "http://<host>:<port>/mcp",
                "headers": {
                    "User-Agent": "..."
                }
            },
            "enable": true
        },
        {
            "type": "sse",
            "params": {
                "url": "https://example.com/sse",
                "headers": {}
            },
            "enable": false
        },
        {
            "type": "stdio",
            "params": {
                "command": "uvx",
                "args": [
                    "mcp-caiyun-weather"
                ],
                "env": {
                    "CAIYUN_WEATHER_API_TOKEN": "xxxxxxxx"
                },
                "cwd": "/path/to/workdir"
            },
            "enable": true
        }
    ]
}
```

- `type`: The type of the MCP backend. Can be `streamable`, `sse`, or `stdio`.
- `params`: Connection-specific parameters.
    - For `streamable` and `sse`: `url` and optional `headers`.
    - For `stdio`: `command`, `args`, `env`, and `cwd` (current working directory).
- `enable`: A boolean to enable or disable the connection to this service.

## Installation

1.  **Prerequisites**:
    - Python 3.8+
    - `uv` (for running the scripts and managing dependencies)

2.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd plugin_mcp_app
    ```

3.  **Install dependencies**:
    ```bash
    uv pip install -r requirements.txt
    ```

4.  **Environment Variables**:
    The plugin relies on environment variables to connect to the MCP Hub. These should be set in the environment where the host application is running.
    - `THING_HOST`: The hostname or IP address of the MCP Hub.
    - `MCP_HUB_PORT`: The port of the MCP Hub.
    - `MCP_HUB_TOKEN`: The authentication token for the MCP Hub API.

## Usage

This project is intended to be run as a plugin within a host system like `xiaozhi_app`. The host system will load and execute `main.py`.

For standalone testing or development, you can run the core proxy directly:

```bash
# This will start the proxy service using the configuration in src/mcp.json
sh ./src/mcp_proxy.sh
```

Or, for more direct execution with `uv`:

```bash
uv run --directory ./src ./mcp_proxy_run.py
```

## License

This project is open-source. Please see the [LICENSE](LICENSE) file for more details.