# export MCP_ENDPOINT="$1"
pid=$(cat src/mcp_pipe.pid 2>/dev/null)
if [ -n "$pid" ]; then
    kill -9 $pid
fi
pid=$(cat src/mcp_pipe.py.pid 2>/dev/null)
if [ -n "$pid" ]; then
    kill -9 $pid
    rm src/mcp_pipe.py.pid
fi
echo $$ > src/mcp_pipe.pid
exec uv run src/mcp_pipe.py
