# -*- coding: utf-8 -*-
"""
API响应数据类
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class APIResponse:
    """API 响应数据"""
    success: bool
    data: Optional[str] = None
    error: Optional[str] = None
    status_code: int = 0
