# -*- coding: utf-8 -*-
"""
全局 HTTP 客户端管理器
复用 aiohttp.ClientSession 避免频繁创建/销毁连接导致系统 socket 耗尽

修复多线程环境问题：
- 每个事件循环维护自己的 session 和 lock
- 避免跨事件循环共享 asyncio 对象
"""
import aiohttp
import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class HTTPClient:
    """
    全局 HTTP 客户端管理器

    解决问题:
    - 每次请求都创建新的 ClientSession 会导致大量 socket 连接
    - 长时间运行后系统 socket 耗尽 (WinError 10055)
    - 多线程环境中事件循环冲突

    使用方法:
        session = await get_shared_session()
        timeout = get_timeout(10)
        async with session.get(url, timeout=timeout) as response:
            ...
    """

    _instance: Optional['HTTPClient'] = None
    # 每个事件循环ID对应自己的session和lock
    _sessions: Dict[int, aiohttp.ClientSession] = {}
    _locks: Dict[int, asyncio.Lock] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._locks = {}
        return cls._instance

    def _get_loop_id(self) -> int:
        """获取当前事件循环的唯一ID"""
        try:
            loop = asyncio.get_running_loop()
            return id(loop)
        except RuntimeError:
            # 没有运行中的事件循环
            return 0

    def _get_lock(self) -> asyncio.Lock:
        """获取当前事件循环对应的锁"""
        loop_id = self._get_loop_id()
        if loop_id not in self._locks:
            self._locks[loop_id] = asyncio.Lock()
        return self._locks[loop_id]

    async def get_session(self) -> aiohttp.ClientSession:
        """
        获取当前事件循环对应的 ClientSession

        Returns:
            aiohttp.ClientSession 实例

        Note:
            - 每个事件循环有独立的 session，避免跨循环问题
            - timeout 需要在每个请求时单独设置
        """
        loop_id = self._get_loop_id()
        lock = self._get_lock()

        async with lock:
            session = self._sessions.get(loop_id)
            if session is None or session.closed:
                # 配置连接池限制，避免创建过多连接
                connector = aiohttp.TCPConnector(
                    limit=100,           # 最大同时连接数
                    limit_per_host=30,   # 每个主机最大连接数
                    ttl_dns_cache=300,   # DNS 缓存时间
                    force_close=False,   # 允许连接复用
                )

                # 不在 session 级别设置 timeout
                session = aiohttp.ClientSession(connector=connector)
                self._sessions[loop_id] = session
                logger.info(f"创建新的 HTTP 客户端 Session (loop_id={loop_id})")

            return session

    async def close(self):
        """关闭当前事件循环对应的 Session"""
        loop_id = self._get_loop_id()
        lock = self._get_lock()

        async with lock:
            session = self._sessions.get(loop_id)
            if session and not session.closed:
                await session.close()
                del self._sessions[loop_id]
                logger.info(f"HTTP 客户端 Session 已关闭 (loop_id={loop_id})")

    async def close_all(self):
        """关闭所有 Session（程序退出时调用）"""
        for loop_id, session in list(self._sessions.items()):
            if session and not session.closed:
                try:
                    await session.close()
                    logger.info(f"HTTP 客户端 Session 已关闭 (loop_id={loop_id})")
                except Exception as e:
                    logger.warning(f"关闭 Session 失败 (loop_id={loop_id}): {e}")
        self._sessions.clear()
        self._locks.clear()


# 全局单例
http_client = HTTPClient()


async def get_shared_session() -> aiohttp.ClientSession:
    """
    便捷函数：获取共享的 HTTP Session

    用法:
        session = await get_shared_session()
        timeout = get_timeout(10)
        async with session.get(url, timeout=timeout) as response:
            ...
    """
    return await http_client.get_session()


def get_timeout(seconds: int = 30) -> aiohttp.ClientTimeout:
    """
    获取 timeout 对象

    Args:
        seconds: 超时秒数

    Returns:
        aiohttp.ClientTimeout 对象
    """
    return aiohttp.ClientTimeout(total=seconds)


async def close_shared_session():
    """关闭当前事件循环的 HTTP Session"""
    await http_client.close()


async def close_all_sessions():
    """关闭所有 HTTP Session（程序退出时调用）"""
    await http_client.close_all()
