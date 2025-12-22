# -*- coding: utf-8 -*-
"""
截图模块

功能:
- CardCapture: 截图和裁剪工具类
- get_card_capture: 获取单例
"""
from .capture import CardCapture, get_card_capture

__all__ = ["CardCapture", "get_card_capture"]
