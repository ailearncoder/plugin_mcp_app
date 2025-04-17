export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_LINK_MODE=copy
if [ ! -f "uv.lock" ]; then
    uv init
    uv add websockets
    uv add python-dotenv
    uv add mcp
    uv add pydantic
    # uv add mcp-proxy
    uv add requests
fi
exec uv run ./src/main.py $1 $2
