# -*- coding: utf-8 -*-
"""
利博API数据获取模块
"""
import asyncio
import zlib
import logging

from core.config import config
from api.response import APIResponse
from api.http_client import get_shared_session, get_timeout

logger = logging.getLogger(__name__)


class APIFetcher:
    """利博API数据获取器"""

    def __init__(self, session_id: str, username: str):
        """
        初始化 API 获取器

        Args:
            session_id: 会话 ID
            username: 用户名
        """
        self.session_id = session_id
        self.username = username

        api_urls = config.get("api.urls", [])
        self.api_url = api_urls[0] if api_urls else ""
        self.skey = config.get("api.skey", "")
        self.jm = config.get("api.jm", 1)
        self.timeout = config.get("api.timeout", 10)

        self._url_index = 0
        self._consecutive_failures = 0

    def update_session(self, session_id: str):
        """更新 sessionID"""
        self.session_id = session_id
        logger.info(f"SessionID 已更新: {session_id[:20]}...")

    def _decrypt(self, data: bytes) -> str:
        """解密 API 响应数据 (gzip/zlib 解压)"""
        # 方法 1: 标准 gzip
        try:
            return zlib.decompress(data, 16 + zlib.MAX_WBITS).decode('utf-8')
        except:
            pass

        # 方法 2: zlib
        try:
            return zlib.decompress(data).decode('utf-8')
        except:
            pass

        # 方法 3: raw deflate
        try:
            return zlib.decompress(data, -zlib.MAX_WBITS).decode('utf-8')
        except:
            pass

        # 方法 4: 直接解码
        try:
            return data.decode('utf-8')
        except:
            pass

        raise ValueError(f"无法解密数据: {data[:50].hex()}")

    async def fetch(self, desk_id: int, act: int = 3) -> APIResponse:
        """
        获取游戏数据

        Args:
            desk_id: 桌号
            act: 动作类型 (0=测试, 3=游戏数据)
        """
        params = {
            "jm": self.jm,
            "skey": self.skey,
            "act": act,
            "desk": desk_id,
            "username": self.username,
            "sessionID": self.session_id
        }

        try:
            session = await get_shared_session()
            timeout = get_timeout(self.timeout)
            async with session.get(self.api_url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    raw_data = await response.read()

                    try:
                        decrypted = self._decrypt(raw_data)
                        self._consecutive_failures = 0
                        return APIResponse(
                            success=True,
                            data=decrypted,
                            status_code=response.status
                        )
                    except ValueError as e:
                        return APIResponse(
                            success=False,
                            error=str(e),
                            status_code=response.status
                        )
                else:
                    self._consecutive_failures += 1
                    return APIResponse(
                        success=False,
                        error=f"HTTP {response.status}",
                        status_code=response.status
                    )

        except asyncio.TimeoutError:
            self._consecutive_failures += 1
            logger.warning(f"[桌{desk_id}] API 请求超时")
            return APIResponse(success=False, error="请求超时")

        except aiohttp.ClientError as e:
            self._consecutive_failures += 1
            logger.error(f"[桌{desk_id}] API 请求失败: {e}")
            return APIResponse(success=False, error=str(e))

        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"[桌{desk_id}] API 未知错误: {e}")
            return APIResponse(success=False, error=str(e))

    async def fetch_game_data(self, desk_id: int) -> APIResponse:
        """获取游戏数据 (act=3)"""
        return await self.fetch(desk_id, act=3)

    async def test_connection(self) -> bool:
        """测试 API 连接"""
        response = await self.fetch(1, act=0)
        if response.success and response.data == "test ok":
            logger.info("API 连接测试成功")
            return True
        logger.warning(f"API 连接测试失败: {response.error}")
        return False

    def switch_api_url(self):
        """切换到备用 API 地址"""
        urls = config.get("api.urls", [])
        self._url_index = (self._url_index + 1) % len(urls)
        self.api_url = urls[self._url_index]
        logger.info(f"切换到备用 API: {self.api_url}")

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
