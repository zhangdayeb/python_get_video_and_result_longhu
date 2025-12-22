# -*- coding: utf-8 -*-
"""
路单同步模块 - 统一管理路单数据同步

调用场景：
1. 进入游戏页面时自动同步
2. 点击"3. 同步路单"按钮
3. 检测到线上铺号与采集铺号不一致时

同步流程：
1. 请求API获取最新roadmap数据
2. 调用后端API进行增量同步
"""
import urllib.request
import urllib.parse
import zlib
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from .config import config

logger = logging.getLogger("roadmap_sync")


def convert_libo_to_mazong(libo_code: str) -> Dict[str, str]:
    """
    将利博编码转换为马总格式 (龙虎版本)

    Args:
        libo_code: 利博编码 (10=龙, 20=和, 30=虎)

    Returns:
        {"result": "1/2/3", "ext": "0", "winner": "龙/虎/和", "pairs": ""}
    """
    result_convert = config.get("result_convert", {})
    converted = result_convert.get(str(libo_code), {"result": "1", "ext": "0"})

    # 添加中文描述 (龙虎版本)
    winner_map = {"1": "龙", "2": "虎", "3": "和"}

    return {
        "result": converted.get("result", "1"),
        "ext": converted.get("ext", "0"),
        "winner": winner_map.get(converted.get("result", "1"), "未知"),
        "pairs": ""  # 龙虎无对子
    }


class RoadmapSyncer:
    """路单同步器"""

    def __init__(self):
        # 回调函数
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_sync_complete: Optional[Callable[[int], None]] = None  # 参数: 写入条数
        self.on_pu_update: Optional[Callable[[int], None]] = None  # 参数: 新铺号
        self.on_shoe_change: Optional[Callable[[], None]] = None  # 换靴回调

        # 凭证缓存
        self.session_id: str = ""
        self.username: str = ""

    def log(self, message: str):
        """输出日志"""
        if self.on_log:
            self.on_log(message)
        logger.info(message)

    def set_credentials(self, session_id: str, username: str):
        """设置API凭证"""
        self.session_id = session_id
        self.username = username

    def sync(self, desk_id: str) -> Dict[str, Any]:
        """
        执行路单同步

        Args:
            desk_id: 桌号

        Returns:
            {
                "success": bool,
                "inserted_count": int,
                "pu_count": int,  # 已完成铺数
                "error": str (可选)
            }
        """
        result = {
            "success": False,
            "inserted_count": 0,
            "pu_count": 0
        }

        # 1. 检查凭证
        self.log(f"[同步] 凭证检查: sessionID={self.session_id[:20] if self.session_id else '空'}..., username={self.username}")
        if not self.session_id:
            result["error"] = "未找到sessionID，请先登录游戏"
            self.log(f"[同步] 错误: {result['error']}")
            return result

        # 2. 请求API获取路单数据
        roadmap_data = self._fetch_roadmap_from_api(desk_id)
        if not roadmap_data:
            result["error"] = "获取路单数据失败"
            return result

        results = roadmap_data.get("results", [])

        # 路单为空说明换靴了，需要发送换靴信号
        # 注意：不要直接发送空记录清空数据，应该通过换靴信号让后端处理
        if not results:
            self.log(f"[同步] 路单为空，检测到换靴")
            result["success"] = True
            result["inserted_count"] = 0
            result["pu_count"] = 0
            result["is_new_shoe"] = True  # 标记换靴
            # 新靴从第1铺开始
            if self.on_sync_complete:
                self.on_sync_complete(0)
            if self.on_pu_update:
                self.on_pu_update(1)
            # 注意：换靴信号由调用方通过 on_shoe_change 回调处理
            # 不在这里直接清空数据库
            return result

        result["pu_count"] = len(results)
        self.log(f"[同步] 获取到 {len(results)} 条路单记录")

        # 3. 写入数据库（增量同步）
        sync_result = self._sync_to_database(desk_id, results)
        result["inserted_count"] = sync_result.get("count", 0)
        result["success"] = sync_result.get("success", False)

        # 4. 回调通知 - 只要同步成功就更新铺号（无论是否有新数据）
        if result["success"]:
            new_pu = len(results) + 1  # 当前进行中的铺号 = 已完成铺数 + 1
            if self.on_sync_complete:
                self.on_sync_complete(len(results))
            if self.on_pu_update:
                self.on_pu_update(new_pu)

        return result

    def _fetch_roadmap_from_api(self, desk_id: str) -> Optional[Dict]:
        """
        从API获取路单数据

        Returns:
            {
                "results": ["30", "10", "20", ...],  # 原始结果编码列表
                "game_id": str,
                "xue": str  # 靴号
            }
        """
        api_url = config.get("api.urls", ["https://apis.796646623.com/httpapi.aspx"])[0]
        skey = config.get("api.skey", "ts123!@")
        jm = config.get("api.jm", 1)

        params = {
            "jm": jm,
            "skey": skey,
            "act": 3,
            "desk": desk_id,
            "username": self.username,
            "sessionID": self.session_id
        }

        url = api_url + "?" + urllib.parse.urlencode(params)
        self.log(f"[同步] 请求API: {api_url[:30]}...")

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")

            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = response.read()
                self.log(f"[同步] 收到 {len(raw_data)} 字节")

                # 解压
                text = self._decompress_response(raw_data)
                if not text:
                    self.log("[同步] 解压失败")
                    return None

                # 解析
                parsed = dict(urllib.parse.parse_qsl(text))
                result_str = parsed.get('result', '')

                if not result_str:
                    self.log("[同步] result字段为空")
                    return None

                results = [r for r in result_str.split('#') if r]
                return {
                    "results": results,
                    "game_id": parsed.get('GameID', ''),
                    "xue": parsed.get('xue', '')
                }

        except Exception as e:
            self.log(f"[同步] API请求失败: {e}")
            return None

    def _decompress_response(self, raw_data: bytes) -> Optional[str]:
        """解压API响应数据"""
        # 尝试 zlib 解压
        try:
            return zlib.decompress(raw_data).decode('utf-8')
        except:
            pass

        # 尝试 gzip 解压
        try:
            return zlib.decompress(raw_data, 16 + zlib.MAX_WBITS).decode('utf-8')
        except:
            pass

        # 直接解码
        try:
            return raw_data.decode('utf-8')
        except:
            pass

        return None

    def _sync_to_database(self, desk_id: str, results: List[str]) -> Dict[str, Any]:
        """
        同步路单数据到后端API

        流程：
        1. 转换利博编码为马总格式
        2. 调用增量同步API

        Args:
            desk_id: 桌号
            results: 路单结果列表 ["30", "10", "20", ...]

        Returns:
            {"success": bool, "count": int, "inserted": int, "updated": int, "skipped": int}
        """
        try:
            from api.online_get_xue_pu import sync_incremental

            self.log(f"[同步] desk_id={desk_id}")
            self.log(f"[同步] 总共获取 {len(results)} 铺路单数据")

            # 显示转换详情的分隔线
            self.log(f"[同步] ========== 转换详情 ==========")

            # 构建同步记录列表
            records = []
            for pu_num, code in enumerate(results, 1):
                # 转换利博编码为马总格式
                converted = convert_libo_to_mazong(code)
                result_value = f"{converted['result']}|{converted['ext']}"

                # 显示转换详情: 铺号 | 利博编码 -> 马总格式(中文含义) - 龙虎版本无对子
                winner = converted.get('winner', '未知')
                self.log(f"[转换] 铺{pu_num}: {code} -> {result_value} ({winner})")

                records.append({
                    "pu_number": pu_num,
                    "libo_result": code
                })

            self.log(f"[同步] ================================")

            # 调用增量同步API
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(sync_incremental(int(desk_id), records))
            loop.close()

            if response.success and response.data:
                inserted = response.data.get('inserted', 0)
                updated = response.data.get('updated', 0)
                skipped = response.data.get('skipped', 0)
                self.log(f"[同步] API同步完成: inserted={inserted}, updated={updated}, skipped={skipped}")
                # 只要API调用成功就算成功（即使全部被跳过）
                return {
                    "success": True,
                    "count": inserted + updated,
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped
                }
            else:
                self.log(f"[同步] API同步失败: {response.error}")
                return {"success": False, "count": 0, "inserted": 0, "updated": 0, "skipped": 0}

        except Exception as e:
            self.log(f"[同步] API同步失败: {e}")
            return {"success": False, "count": 0, "inserted": 0, "updated": 0, "skipped": 0}

    def get_local_last_n_results(self, desk_id: str, n: int = 2) -> List[str]:
        """
        从利博API获取最后N条路单结果（转换为马总格式）

        用于与线上数据库比对

        Args:
            desk_id: 桌号
            n: 获取数量，默认2条

        Returns:
            result值列表，按铺号降序 ["2|0", "1|0"]
        """
        if not self.session_id:
            return []

        # 获取利博API路单数据
        roadmap_data = self._fetch_roadmap_from_api(desk_id)
        if not roadmap_data:
            return []

        results = roadmap_data.get("results", [])
        if not results:
            return []

        # 取最后N条并转换格式
        last_n = results[-n:] if len(results) >= n else results
        # 按铺号降序排列（最新的在前）
        last_n = list(reversed(last_n))

        converted_results = []
        for code in last_n:
            converted = convert_libo_to_mazong(code)
            result_value = f"{converted['result']}|{converted['ext']}"
            converted_results.append(result_value)

        return converted_results


# 全局单例
roadmap_syncer = RoadmapSyncer()
