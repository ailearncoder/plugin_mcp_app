import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING
import socket
from importlib.resources import files

if TYPE_CHECKING:
    from aiohttp import web
else:
    try:
        from aiohttp import web
    except ImportError:
        web = None  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigServer:
    """HTTP 服务器用于管理 MCP 服务器配置文件"""
    
    def __init__(self, config_dir: str, port: int = 0, on_config_update: Optional[Callable] = None):
        """
        初始化配置服务器
        
        Args:
            config_dir: 配置文件目录
            port: 监听端口，0 表示自动分配
            on_config_update: 配置更新时的回调函数
        """
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "mcp_servers.json"
        self.port = port
        self.host = "127.0.0.1"
        self.on_config_update = on_config_update
        
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._server_task: Optional[asyncio.Task] = None
        
        # 确保配置目录和文件存在
        self._init_config_file()
    
    def _init_config_file(self):
        """初始化配置文件，如果不存在则从 assets 复制"""
        if not self.config_file.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # 从 assets 复制默认配置
            try:
                data_path = files('plugin_mcp_app').joinpath('assets')
                default_config = data_path.joinpath('mcp_servers.json')
                
                if default_config.is_file():
                    config_content = default_config.read_text()
                    self.config_file.write_text(config_content)
                    logger.info(f"已从 assets 复制配置文件到: {self.config_file}")
                else:
                    # 创建默认配置
                    default_data = {"mcpServers": {}}
                    self.config_file.write_text(json.dumps(default_data, indent=4, ensure_ascii=False))
                    logger.info(f"已创建默认配置文件: {self.config_file}")
            except Exception as e:
                logger.error(f"初始化配置文件失败: {e}")
                # 创建空配置
                default_data = {"mcpServers": {}}
                self.config_file.write_text(json.dumps(default_data, indent=4, ensure_ascii=False))
    
    def _find_free_port(self) -> int:
        """找一个可用的端口"""
        if self.port != 0:
            return self.port
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    async def _handle_index(self, request: web.Request) -> web.Response:
        """处理首页请求，返回 index.html"""
        try:
            data_path = files('plugin_mcp_app').joinpath('assets')
            index_file = data_path.joinpath('index.html')
            
            if index_file.is_file():
                content = index_file.read_text(encoding='utf-8')
                return web.Response(text=content, content_type='text/html', charset='utf-8')
            else:
                return web.Response(text='index.html not found', status=404)
        except Exception as e:
            logger.error(f"读取 index.html 失败: {e}")
            return web.Response(text=f'Error loading page: {str(e)}', status=500)
    
    async def _handle_get_config(self, request: web.Request) -> web.Response:
        """获取配置文件内容"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                return web.json_response(config_data)
            else:
                return web.json_response({"mcpServers": {}})
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_save_config(self, request: web.Request) -> web.Response:
        """保存配置文件"""
        try:
            data = await request.json()
            
            # 保存到文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            logger.info(f"配置文件已更新: {self.config_file}")
            
            # 触发回调
            if self.on_config_update:
                try:
                    if asyncio.iscoroutinefunction(self.on_config_update):
                        await self.on_config_update(data)
                    else:
                        self.on_config_update(data)
                except Exception as e:
                    logger.error(f"配置更新回调执行失败: {e}")
            
            return web.json_response({"success": True, "message": "配置已保存"})
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    def _setup_routes(self):
        """设置路由"""
        if self.app is not None:
            self.app.router.add_get('/', self._handle_index)
            self.app.router.add_get('/api/config', self._handle_get_config)
            self.app.router.add_post('/api/config', self._handle_save_config)
    
    async def start(self) -> str:
        """
        启动 HTTP 服务器
        
        Returns:
            服务器地址 (http://127.0.0.1:port)
        """
        if self.runner is not None:
            logger.warning("服务器已经在运行中")
            return self.get_server_url()
        
        if web is None:
            raise RuntimeError("aiohttp 未安装，请运行: pip install aiohttp")
        
        # 创建应用
        self.app = web.Application()
        self._setup_routes()
        
        # 找一个可用端口
        self.port = self._find_free_port()
        
        # 启动服务器
        self.runner = web.AppRunner(self.app)
        if self.runner is not None:
            await self.runner.setup()
        
            self.site = web.TCPSite(self.runner, self.host, self.port)
            if self.site is not None:
                await self.site.start()
        
        server_url = self.get_server_url()
        logger.info(f"配置服务器已启动: {server_url}")
        
        return server_url
    
    async def stop(self):
        """关闭 HTTP 服务器"""
        if self.runner is None:
            logger.warning("服务器未运行")
            return
        
        try:
            await self.runner.cleanup()
            logger.info("配置服务器已关闭")
        except Exception as e:
            logger.error(f"关闭服务器失败: {e}")
        finally:
            self.runner = None
            self.site = None
            self.app = None
    
    def get_server_url(self) -> str:
        """获取服务器地址"""
        if self.port == 0:
            raise RuntimeError("服务器未启动")
        return f"http://{self.host}:{self.port}"
    
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self.runner is not None
    
    async def run_forever(self):
        """持续运行服务器直到被停止"""
        await self.start()
        try:
            # 保持运行
            while True:
                await asyncio.sleep(3600)  # 每小时检查一次
        except asyncio.CancelledError:
            logger.info("服务器任务被取消")
        finally:
            await self.stop()


# 示例使用
if __name__ == "__main__":
    async def on_update(config_data):
        """配置更新回调示例"""
        print(f"配置已更新: {config_data}")
    
    async def main():
        # 创建服务器实例
        server = ConfigServer(
            config_dir="./config",
            port=0,  # 可以指定端口或使用 0 自动分配
            on_config_update=on_update
        )
        
        # 启动服务器
        url = await server.start()
        print(f"服务器运行在: {url}")
        print(f"在浏览器中打开: {url}")
        
        try:
            # 保持运行
            await asyncio.sleep(3600)  # 运行 1 小时
        finally:
            # 关闭服务器
            await server.stop()
    
    asyncio.run(main())