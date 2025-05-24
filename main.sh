export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_EXTRA_INDEX_URL=https://pypi.mac.axyz.cc:30923/simple
export UV_INSECURE_HOST=pypi.mac.axyz.cc
export UV_LINK_MODE=copy
export LOG_LEVEL=INFO
if [ ! -f "uv.lock" ]; then
    uv init
    uv add websockets
    uv add python-dotenv
    uv add mcp
    uv add pydantic
    # uv add mcp-proxy
    uv add requests
    uv add xiaozhi_app
fi
exec uv run ./src/main.py $1 $2
