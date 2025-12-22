# -*- coding: utf-8 -*-
"""
开局信号API - 发送开始下注信号
"""
import logging

import aiohttp

from core.config import config
from api.response import APIResponse

logger = logging.getLogger(__name__)


async def send_start_signal(desk_id: int, countdown_time: int = 45) -> APIResponse:
    """
    发送开局信号 (开始下注)

    Args:
        desk_id: 利博桌号
        countdown_time: 倒计时秒数

    Returns:
        APIResponse
    """
    base_url = config.get("backend_api.base_url", "")
    endpoints = config.get("backend_api.endpoints", {})
    timeout = aiohttp.ClientTimeout(total=config.get("backend_api.timeout", 10))
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}{endpoints.get('start_signal', '')}"
    params = {
        "tableId": table_id,
        "time": countdown_time
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.text()
                    logger.info(f"[桌{desk_id}] 开局信号发送成功")
                    return APIResponse(success=True, data=data, status_code=response.status)
                else:
                    logger.error(f"[桌{desk_id}] 开局信号发送失败: HTTP {response.status}")
                    return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 开局信号发送异常: {e}")
        return APIResponse(success=False, error=str(e))
