# -*- coding: utf-8 -*-
"""
FLV 推流自动登录模块

包含:
1. FLVLogin - FLV 浏览器登录（获取 FLV URL）
2. FLVSession - FLV 签名管理（监控过期、刷新）
"""

from .login import FLVLogin
from .session import FLVSession

# 全局单例
flv_login = FLVLogin()
flv_session = FLVSession()

__all__ = [
    'FLVLogin',
    'FLVSession',
    'flv_login',
    'flv_session',
]
