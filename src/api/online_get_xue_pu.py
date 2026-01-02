# -*- coding: utf-8 -*-
"""
获取靴号铺号API - 从后端获取当前靴号和铺号
"""
import logging
from typing import Optional

from core.config import config
from api.response import APIResponse
from api.http_client import get_shared_session, get_timeout

logger = logging.getLogger(__name__)

# 通用请求头
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


async def get_current_xue_pu(desk_id: int) -> APIResponse:
    """
    从后端API获取当前靴号和铺号

    Args:
        desk_id: 桌号

    Returns:
        APIResponse with data: {xue_number, pu_number, last_result, last_update_time}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/get_table/current_xue_pu"
    params = {"table_id": table_id}

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 获取靴号铺号成功: xue={result_data.get('xue_number')}, pu={result_data.get('pu_number')}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 获取靴号铺号业务失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 获取靴号铺号失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 获取靴号铺号异常: {e}")
        return APIResponse(success=False, error=str(e))


async def get_roadmap_full(desk_id: int, xue_number: Optional[int] = None) -> APIResponse:
    """
    获取整靴露珠数据

    Args:
        desk_id: 桌号
        xue_number: 靴号(可选，不传则获取当前靴)

    Returns:
        APIResponse with data: {table_id, xue_number, total_pu, current_pu, records}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/get_table/roadmap_full"
    params = {"table_id": table_id}
    if xue_number is not None:
        params["xue_number"] = xue_number

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 获取整靴露珠成功: xue={result_data.get('xue_number')}, total_pu={result_data.get('total_pu')}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 获取整靴露珠业务失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 获取整靴露珠失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 获取整靴露珠异常: {e}")
        return APIResponse(success=False, error=str(e))


async def get_caiji_config(desk_id: int) -> APIResponse:
    """
    获取采集配置

    Args:
        desk_id: 桌号

    Returns:
        APIResponse with data: {caiji_username, caiji_password, caiji_desk_url, caiji_flv_username, caiji_flv_password}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/get_table/caiji_config"
    params = {"table_id": table_id}

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 获取采集配置成功: user={result_data.get('caiji_username')}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 获取采集配置失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 获取采集配置失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 获取采集配置异常: {e}")
        return APIResponse(success=False, error=str(e))


async def get_last_n_results(desk_id: int, n: int = 2) -> APIResponse:
    """
    获取最后N条露珠结果（用于同步比对）

    Args:
        desk_id: 桌号
        n: 获取数量，默认2

    Returns:
        APIResponse with data: {table_id, count, results[]}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/luzhu/get_last_n"
    params = {"table_id": table_id, "n": n}

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 获取最后{n}条结果成功: count={result_data.get('count')}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 获取最后{n}条结果失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 获取最后{n}条结果失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 获取最后{n}条结果异常: {e}")
        return APIResponse(success=False, error=str(e))


async def sync_incremental(desk_id: int, records: list) -> APIResponse:
    """
    增量同步露珠数据（龙虎专用，game_type=2）

    Args:
        desk_id: 桌号
        records: 记录列表 [{"pu_number": 14, "libo_result": "30"}, ...]

    Returns:
        APIResponse with data: {inserted, updated, skipped, errors[], xue_number}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/luzhu/sync_incremental"
    payload = {
        "table_id": table_id,
        "records": records,
        "game_type": 2  # 龙虎固定为2
    }

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.post(url, json=payload, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 增量同步成功: inserted={result_data.get('inserted')}, updated={result_data.get('updated')}, skipped={result_data.get('skipped')}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 增量同步业务失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 增量同步失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 增量同步异常: {e}")
        return APIResponse(success=False, error=str(e))


async def delete_excess_records(desk_id: int, keep_pu_number: int) -> APIResponse:
    """
    删除多余的露珠记录（当线上数据比采集源多时使用）

    Args:
        desk_id: 桌号
        keep_pu_number: 保留到这个铺号，删除之后的所有记录

    Returns:
        APIResponse with data: {deleted, deleted_pu_numbers[], keep_pu_number, xue_number}
    """
    base_url = config.get("backend_api.base_url", "")
    timeout = config.get("backend_api.timeout", 10)
    desk_mapping = config.desk_mapping

    table_id = desk_mapping.get(str(desk_id), desk_id)
    url = f"{base_url}/bjl/luzhu/delete_excess"
    payload = {
        "table_id": table_id,
        "keep_pu_number": keep_pu_number
    }

    try:
        session = await get_shared_session()
        timeout_obj = get_timeout(timeout)
        async with session.post(url, json=payload, headers=DEFAULT_HEADERS, timeout=timeout_obj) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if data.get('code') == 200:
                    result_data = data.get('data', {})
                    logger.info(f"[桌{desk_id}] 删除多余记录成功: deleted={result_data.get('deleted')}, keep_pu={keep_pu_number}")
                    return APIResponse(success=True, data=result_data, status_code=response.status)
                else:
                    logger.warning(f"[桌{desk_id}] 删除多余记录失败: {data.get('message')}")
                    return APIResponse(success=False, error=data.get('message', 'Unknown error'), status_code=response.status)

            logger.error(f"[桌{desk_id}] 删除多余记录失败: HTTP {response.status}")
            return APIResponse(success=False, error=f"HTTP {response.status}", status_code=response.status)
    except Exception as e:
        logger.error(f"[桌{desk_id}] 删除多余记录异常: {e}")
        return APIResponse(success=False, error=str(e))
