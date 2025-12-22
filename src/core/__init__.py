# -*- coding: utf-8 -*-
"""
核心模块

包含以下组件:
- config: 配置管理器
- db: 数据库管理器
- roadmap_syncer: 路单同步器
- game_processor: 游戏处理器
- setup_logger/get_logger: 日志工具
"""
from .config import config
from .database import db
from .logger import setup_logger, get_logger
from .roadmap_sync import roadmap_syncer
from .game_processor import game_processor

__all__ = [
    "config",
    "db",
    "setup_logger",
    "get_logger",
    "roadmap_syncer",
    "game_processor"
]
