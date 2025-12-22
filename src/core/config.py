# -*- coding: utf-8 -*-
"""
配置管理器 - 统一管理所有配置

支持多开：通过 set_runtime_config() 设置运行时配置
"""
import json
from pathlib import Path
from typing import Any, Dict, List


class ConfigManager:
    """配置管理器 - 单例模式"""

    _instance = None
    _config: Dict[str, Any] = None

    # 运行时配置（支持多开）
    _runtime_desk_id: int = 1
    _runtime_debug_port: int = 9223

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self.load()

    def load(self, config_path: str = None):
        """加载配置文件"""
        if config_path is None:
            # config.json 在项目根目录 (src 的上一级)
            config_file = Path(__file__).parent.parent.parent / "config.json"
        else:
            config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_file}")

        with open(config_file, 'r', encoding='utf-8') as f:
            self._config = json.load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号路径）

        Example:
            config.get("mysql.host")  # "13.212.181.21"
            config.get("api.urls")    # ["https://...", ...]
        """
        if self._config is None:
            self.load()

        keys = key_path.split('.')
        value = self._config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        if self._config is None:
            self.load()
        return self._config

    # ========== 快捷属性 ==========

    @property
    def api_urls(self) -> List[str]:
        return self.get("api.urls", [])

    @property
    def api_skey(self) -> str:
        return self.get("api.skey", "")

    @property
    def api_timeout(self) -> int:
        return self.get("api.timeout", 10)

    @property
    def mysql_config(self) -> Dict[str, Any]:
        return self.get("mysql", {})

    @property
    def backend_api_base_url(self) -> str:
        return self.get("backend_api.base_url", "")

    @property
    def backend_api_endpoints(self) -> Dict[str, str]:
        return self.get("backend_api.endpoints", {})

    @property
    def desk_mapping(self) -> Dict[str, int]:
        return self.get("desk_mapping", {})

    @property
    def desk_names(self) -> Dict[str, str]:
        return self.get("desk_names", {})

    @property
    def browser_config(self) -> Dict[str, Any]:
        return self.get("browser", {})

    def get_table_id(self, desk_id: int) -> int:
        """根据桌号获取 table_id"""
        mapping = self.desk_mapping
        return mapping.get(str(desk_id), desk_id)

    def get_desk_name(self, desk_id: int) -> str:
        """根据桌号获取桌台名称"""
        names = self.desk_names
        return names.get(str(desk_id), f"F{desk_id}")

    # ========== 多开支持 ==========

    def set_runtime_config(self, desk_id: int, debug_port: int):
        """
        设置运行时配置（支持多开）

        Args:
            desk_id: 桌号 (1-6)
            debug_port: 浏览器调试端口
        """
        self._runtime_desk_id = desk_id
        self._runtime_debug_port = debug_port

    @property
    def runtime_desk_id(self) -> int:
        """当前运行实例的桌号"""
        return self._runtime_desk_id

    @property
    def runtime_debug_port(self) -> int:
        """当前运行实例的调试端口"""
        return self._runtime_debug_port

    @property
    def base_dir(self) -> Path:
        """项目根目录"""
        return Path(__file__).parent.parent.parent

    @property
    def instance_dir(self) -> Path:
        """当前实例的专属目录: temp/desk_X/"""
        return self.base_dir / "temp" / f"desk_{self._runtime_desk_id}"

    def get_instance_path(self, subdir: str) -> Path:
        """
        获取实例专属子目录路径

        Args:
            subdir: 子目录名，如 "logs", "screenshots", "chromium_user_data"

        Returns:
            完整路径，如 temp/desk_1/screenshots/
        """
        path = self.instance_dir / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def instance_logs_dir(self) -> Path:
        """实例日志目录"""
        return self.get_instance_path("logs")

    @property
    def instance_screenshots_dir(self) -> Path:
        """实例截图目录"""
        return self.get_instance_path("screenshots")

    @property
    def instance_browser_data_dir(self) -> Path:
        """实例浏览器数据目录"""
        return self.get_instance_path("chromium_user_data")


# 全局单例
config = ConfigManager()
