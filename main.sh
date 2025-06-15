export UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple
export UV_EXTRA_INDEX_URL=https://pypi.mac.axyz.cc:30923/simple
export UV_INSECURE_HOST=pypi.mac.axyz.cc
export UV_LINK_MODE=copy
export LOG_LEVEL=INFO
if [ ! -f ".init" ]; then
    if [ ! -f pyproject.toml ]; then
        uv init
    fi
    uv add mcp
    uv add requests
    uv add xiaozhi_app
    touch .init
fi
exec uv run --active ./src/main.py $1 $2
