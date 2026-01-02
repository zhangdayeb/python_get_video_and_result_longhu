# -*- coding: utf-8 -*-
"""
换靴信号API - 发送换靴信号
"""
import logging

from core.config import config
from api.response import APIResponse
from api.http_client import get_shared_session, get_timeout

logger = logging.getLogger(__name__)


async def send_add_xue(desk_id: int, game_type: int = 2) -> APIResponse:
    """
    发送换靴信号 (龙虎版本)

    Args:
        desk_id: 利博桌号
        game_type: 游戏类型 (2=龙虎)

    Returns:
        APIResponse
    """
    base_url = config.get("backend_api.base_url", "")
    endpoints = config.get("backend_api.endpoints", {})
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}{endpoints.get('add_xue', '')}"
    params = {
        "tableId": table_id,
        "num_xue": 1,
        "gameType": game_type
    }

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.get(url, params=params, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.text()
                logger.info(f"[桌{desk_id}] 换靴信号发送成功")
                return APIResponse(success=True, data=data, status_code=response.status)
            else:
                logger.error(f"[桌{desk_id}] 换靴信号发送失败: HTTP {response.status}")
                return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 换靴信号发送异常: {e}")
        return APIResponse(success=False, error=str(e))
