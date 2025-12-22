# -*- coding: utf-8 -*-
"""
日志管理器
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(
    name: str,
    log_file: str = None,
    level: int = logging.INFO,
    console: bool = True
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志名称
        log_file: 日志文件路径 (可选)
        level: 日志级别
        console: 是否输出到控制台

    Returns:
        Logger实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 格式
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S'
    )

    # 控制台输出
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """获取已存在的日志记录器"""
    return logging.getLogger(name)


def setup_process_logger(process_name: str) -> logging.Logger:
    """
    为进程设置专用日志

    Args:
        process_name: 进程名称

    Returns:
        Logger实例
    """
    # 使用实例专属的日志目录 (支持多开)
    from core.config import config
    log_dir = config.instance_logs_dir
    log_file = log_dir / f"{process_name}.log"

    return setup_logger(process_name, str(log_file))
