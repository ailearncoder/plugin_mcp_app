export UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple
export UV_EXTRA_INDEX_URL=https://pypi.mac.axyz.cc:30923/simple
export UV_INSECURE_HOST=pypi.mac.axyz.cc
export UV_LINK_MODE=copy
export LOG_LEVEL=INFO
if [ ! -f ".init" ]; then
    echo "正在初始化"
    if [ ! -f pyproject.toml ]; then
        echo "正在初始化 python 环境"
        uv init
    fi
    echo "正在安装模块：mcp"
    uv add mcp
    echo "正在安装模块：requests"
    uv add requests
    echo "正在安装模块：xiaozhi_app"
    uv add xiaozhi_app
    if [ -f ZeroSSL_ECC_Domain_Secure_Site_CA.pem ]; then
        cacert_file=`find ./.venv -type f -name "*.pem" | head -1`
        if [ "$cacert_file" != "" ]; then
            echo "正在安装证书:ZeroSSL_ECC_Domain_Secure_Site_CA 到 $cacert_file"
            cat ZeroSSL_ECC_Domain_Secure_Site_CA.pem >> $cacert_file
        else
            echo "未找到证书文件"
        fi
    fi
    echo "初始化完成"
    touch .init
fi
echo "开始运行程序"
exec uv run --active ./src/main.py $1 $2
