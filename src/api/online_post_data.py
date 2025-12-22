# -*- coding: utf-8 -*-
"""
开牌数据API - 发送开牌结果
"""
import logging
from typing import Dict

import aiohttp

from core.config import config
from api.response import APIResponse

logger = logging.getLogger(__name__)


async def send_open_card(
    desk_id: int,
    xue_number: int,
    pu_number: int,
    result: str,
    ext: str,
    pai_result: Dict[str, str],
    is_simulated: int = 0
) -> APIResponse:
    """
    发送开牌结果 (龙虎版本)

    Args:
        desk_id: 桌号
        xue_number: 靴号
        pu_number: 铺号
        result: 结果 (1=龙, 2=虎, 3=和)
        ext: 固定为0 (龙虎无对子)
        pai_result: 牌面数据
        is_simulated: 是否模拟数据 (0=AI识别真实数据, 1=模拟填充数据)

    Returns:
        APIResponse
    """
    base_url = config.get("backend_api.base_url", "")
    endpoints = config.get("backend_api.endpoints", {})
    timeout = aiohttp.ClientTimeout(total=config.get("backend_api.timeout", 10))
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}{endpoints.get('post_data', '')}"

    data = {
        "tableId": table_id,
        "gameType": 2,  # 龙虎
        "xueNumber": xue_number,
        "puNumber": pu_number,
        "result": result,
        "ext": ext,
        "pai_result": pai_result,
        "is_simulated": is_simulated
    }

    logger.info(f"[桌{desk_id}] 发送开牌: URL={url}, data={data}")

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=data) as response:
                resp_data = await response.text()
                logger.info(f"[桌{desk_id}] 响应: HTTP {response.status}, body={resp_data[:200]}")

                if response.status == 200:
                    sim_tag = "[模拟]" if is_simulated else ""
                    logger.info(f"[桌{desk_id}] {sim_tag}开牌结果发送成功: {result}|{ext}")
                    return APIResponse(success=True, data=resp_data, status_code=response.status)
                else:
                    logger.error(f"[桌{desk_id}] 开牌结果发送失败: HTTP {response.status}, resp={resp_data}")
                    return APIResponse(success=False, error=f"HTTP {response.status}: {resp_data}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 开牌结果发送异常: {e}")
        return APIResponse(success=False, error=str(e))
