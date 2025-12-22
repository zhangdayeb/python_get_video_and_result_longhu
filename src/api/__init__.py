# -*- coding: utf-8 -*-
"""
API模块

包含以下组件:
- APIResponse: API响应数据类
- APIFetcher: 利博数据获取器
- BackendAPI: 后端API组合类
- send_start_signal: 开局信号
- send_end_signal: 结束信号
- send_open_card: 开牌结果
- send_add_xue: 换靴信号
"""
from .response import APIResponse
from .libo_fetcher import APIFetcher
from .backend import BackendAPI
from .online_start import send_start_signal
from .online_end import send_end_signal
from .online_post_data import send_open_card
from .online_add_xue import send_add_xue

__all__ = [
    "APIResponse",
    "APIFetcher",
    "BackendAPI",
    "send_start_signal",
    "send_end_signal",
    "send_open_card",
    "send_add_xue"
]
