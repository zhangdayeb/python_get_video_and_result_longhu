# -*- coding: utf-8 -*-
"""
路单采集自动登录模块

包含:
1. RoadmapLogin - 路单浏览器登录
2. RoadmapSession - Session 监控与自动重登
3. RoadmapLogout - 退出登录
"""

from .login import RoadmapLogin
from .session import RoadmapSession
from .logout import RoadmapLogout

# 全局单例
roadmap_login = RoadmapLogin()
roadmap_session = RoadmapSession()
roadmap_logout = RoadmapLogout()

__all__ = [
    'RoadmapLogin',
    'RoadmapSession',
    'RoadmapLogout',
    'roadmap_login',
    'roadmap_session',
    'roadmap_logout',
]
