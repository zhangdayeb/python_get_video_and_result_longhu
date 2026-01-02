# -*- coding: utf-8 -*-
"""
后端API组合类 - 封装所有后端接口调用
"""
import logging
from typing import Dict, Optional

from core.config import config
from api.response import APIResponse
from api.online_start import send_start_signal
from api.online_end import send_end_signal
from api.online_post_data import send_open_card
from api.online_add_xue import send_add_xue
from api.online_get_xue_pu import get_current_xue_pu, get_roadmap_full, get_caiji_config, get_last_n_results, sync_incremental
from api.http_client import get_shared_session, get_timeout

logger = logging.getLogger(__name__)


class BackendAPI:
    """后端 API 组合类 - 提供统一的接口调用入口"""

    def __init__(self):
        self.base_url = config.get("backend_api.base_url", "")
        self.timeout = config.get("backend_api.timeout", 10)

    async def send_start_signal(self, desk_id: int, countdown_time: int = 45) -> APIResponse:
        """发送开局信号 (开始下注)"""
        return await send_start_signal(desk_id, countdown_time)

    async def send_end_signal(self, desk_id: int) -> APIResponse:
        """发送结束信号 (停止下注)"""
        return await send_end_signal(desk_id)

    async def send_open_card(
        self,
        desk_id: int,
        xue_number: int,
        pu_number: int,
        result: str,
        ext: str,
        pai_result: Dict[str, str],
        is_simulated: int = 0
    ) -> APIResponse:
        """发送开牌结果"""
        return await send_open_card(desk_id, xue_number, pu_number, result, ext, pai_result, is_simulated)

    async def send_add_xue(self, desk_id: int, game_type: int = 2) -> APIResponse:
        """发送换靴信号 (龙虎版本)"""
        return await send_add_xue(desk_id, game_type)

    async def get_current_xue_pu(self, desk_id: int) -> APIResponse:
        """获取当前靴号铺号"""
        return await get_current_xue_pu(desk_id)

    async def get_roadmap_full(self, desk_id: int, xue_number: Optional[int] = None) -> APIResponse:
        """获取整靴露珠数据"""
        return await get_roadmap_full(desk_id, xue_number)

    async def get_caiji_config(self, desk_id: int) -> APIResponse:
        """获取采集配置"""
        return await get_caiji_config(desk_id)

    async def get_last_n_results(self, desk_id: int, n: int = 2) -> APIResponse:
        """获取最后N条露珠结果"""
        return await get_last_n_results(desk_id, n)

    async def sync_incremental(self, desk_id: int, records: list) -> APIResponse:
        """增量同步露珠数据"""
        return await sync_incremental(desk_id, records)

    async def test_connection(self) -> bool:
        """测试后端 API 连接"""
        try:
            url = f"{self.base_url}/bjl/get_table/list"
            session = await get_shared_session()
            timeout = get_timeout(self.timeout)
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    logger.info("后端 API 连接测试成功")
                    return True
                else:
                    logger.warning(f"后端 API 连接测试失败: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"后端 API 连接测试异常: {e}")
            return False
